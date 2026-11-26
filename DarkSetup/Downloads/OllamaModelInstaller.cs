using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using DarkSetup.Manifest;

namespace DarkSetup.Downloads;

public sealed record ModelPullProgress(string ModelId, string Status, long? Completed, long? Total);
public sealed record ModelInstallResult(string ModelId, string Digest, long SizeBytes, bool AlreadyInstalled);
public sealed record OllamaInstalledModel(string Name, string Digest, long SizeBytes);

public sealed class OllamaModelInstaller(HttpClient httpClient, Uri apiBaseUri)
{
    private static readonly JsonSerializerOptions JsonOptions = new() { PropertyNameCaseInsensitive = true };

    public async Task<ModelInstallResult> InstallAsync(
        VerifiedManifest manifest,
        string modelId,
        long? availableFreeBytes,
        IProgress<ModelPullProgress>? progress = null,
        CancellationToken cancellationToken = default)
    {
        var model = manifest.Payload.Models.SingleOrDefault(candidate => candidate.Id == modelId)
            ?? throw new KeyNotFoundException($"El modelo {modelId} no está en el catálogo firmado.");
        ValidateLocalApiUri();

        var tags = await ReadTagsAsync(cancellationToken);
        var localModel = tags.Models.FirstOrDefault(entry =>
            entry.Name.Equals(model.ModelTag, StringComparison.OrdinalIgnoreCase));
        if (localModel is not null)
        {
            if (!DigestEquals(localModel.Digest, model.Digest))
                throw new InvalidDataException(
                    $"{model.ModelTag} ya existe en Ollama con un digest distinto; no se sobrescribió.");
            return new ModelInstallResult(model.Id, localModel.Digest, localModel.Size, AlreadyInstalled: true);
        }
        if (availableFreeBytes is null || availableFreeBytes < model.MaximumDownloadBytes)
            throw new IOException($"No se confirmó espacio libre suficiente para descargar {model.ModelTag}.");

        var pullUri = ApiUri("api/pull");
        using var request = new HttpRequestMessage(HttpMethod.Post, pullUri)
        {
            Content = JsonContent.Create(new { model = model.ModelTag, stream = true }),
        };
        using var response = await httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        response.EnsureSuccessStatusCode();
        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        using var reader = new StreamReader(stream);
        var succeeded = false;
        while (await reader.ReadLineAsync(cancellationToken) is { } line)
        {
            if (line.Length > 64 * 1024) throw new InvalidDataException("Ollama devolvió un estado de descarga demasiado grande.");
            if (string.IsNullOrWhiteSpace(line)) continue;
            using var status = JsonDocument.Parse(line);
            var root = status.RootElement;
            if (root.TryGetProperty("error", out var error))
                throw new InvalidOperationException($"Ollama rechazó la descarga de {model.ModelTag}: {error.GetString()}");
            var label = root.TryGetProperty("status", out var state) ? state.GetString() ?? "" : "";
            var completed = ReadLong(root, "completed");
            var total = ReadLong(root, "total");
            if (total is > 0 && total > model.MaximumDownloadBytes)
                throw new InvalidDataException($"El tamaño anunciado por Ollama excede el límite firmado para {model.Id}.");
            progress?.Report(new ModelPullProgress(model.Id, label, completed, total));
            if (label.Equals("success", StringComparison.OrdinalIgnoreCase)) succeeded = true;
        }
        if (!succeeded) throw new EndOfStreamException($"Ollama terminó la descarga de {model.ModelTag} sin confirmar success.");

        var installed = (await ReadTagsAsync(cancellationToken)).Models.FirstOrDefault(entry =>
            entry.Name.Equals(model.ModelTag, StringComparison.OrdinalIgnoreCase));
        if (installed is null || !DigestEquals(installed.Digest, model.Digest))
            throw new InvalidDataException($"Ollama instaló {model.ModelTag}, pero su digest no coincide con el catálogo firmado.");
        if (installed.Size > model.MaximumDownloadBytes)
            throw new InvalidDataException($"El tamaño instalado de {model.ModelTag} excede el límite firmado.");
        return new ModelInstallResult(model.Id, installed.Digest, installed.Size, AlreadyInstalled: false);
    }

    public async Task<ModelInstallResult> InstallCustomAsync(
        string modelTag,
        bool userConfirmedDownload,
        IProgress<ModelPullProgress>? progress = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(modelTag);
        if (modelTag.Length > 200 || modelTag.Any(char.IsControl) || modelTag.Any(char.IsWhiteSpace)
            || modelTag.StartsWith('/') || modelTag.EndsWith('/') || modelTag.Contains("..", StringComparison.Ordinal))
            throw new ArgumentException("La etiqueta Ollama personalizada no tiene un formato válido.", nameof(modelTag));
        ValidateLocalApiUri();
        var tags = await ReadTagsAsync(cancellationToken);
        var local = tags.Models.FirstOrDefault(entry => entry.Name.Equals(modelTag, StringComparison.OrdinalIgnoreCase));
        if (local is not null)
            return new ModelInstallResult(modelTag, local.Digest, local.Size, AlreadyInstalled: true);
        if (!userConfirmedDownload)
            throw new InvalidOperationException("La descarga de una etiqueta personalizada requiere confirmación explícita del usuario.");

        using var request = new HttpRequestMessage(HttpMethod.Post, ApiUri("api/pull"))
        {
            Content = JsonContent.Create(new { model = modelTag, stream = true }),
        };
        using var response = await httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        response.EnsureSuccessStatusCode();
        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        using var reader = new StreamReader(stream);
        var succeeded = false;
        while (await reader.ReadLineAsync(cancellationToken) is { } line)
        {
            if (line.Length > 64 * 1024) throw new InvalidDataException("Ollama devolvió un estado de descarga demasiado grande.");
            if (string.IsNullOrWhiteSpace(line)) continue;
            using var status = JsonDocument.Parse(line);
            var root = status.RootElement;
            if (root.TryGetProperty("error", out var error))
                throw new InvalidOperationException($"Ollama rechazó la descarga de {modelTag}: {error.GetString()}");
            var label = root.TryGetProperty("status", out var state) ? state.GetString() ?? "" : "";
            progress?.Report(new ModelPullProgress(modelTag, label, ReadLong(root, "completed"), ReadLong(root, "total")));
            if (label.Equals("success", StringComparison.OrdinalIgnoreCase)) succeeded = true;
        }
        if (!succeeded) throw new EndOfStreamException($"Ollama terminó la descarga de {modelTag} sin confirmar success.");
        var installed = (await ReadTagsAsync(cancellationToken)).Models.FirstOrDefault(entry =>
            entry.Name.Equals(modelTag, StringComparison.OrdinalIgnoreCase));
        if (installed is null) throw new InvalidDataException($"Ollama no muestra {modelTag} después de la descarga.");
        return new ModelInstallResult(modelTag, installed.Digest, installed.Size, AlreadyInstalled: false);
    }

    public async Task<IReadOnlyDictionary<string, string>> ReadInstalledDigestsAsync(
        CancellationToken cancellationToken = default)
    {
        ValidateLocalApiUri();
        var tags = await ReadTagsAsync(cancellationToken);
        return tags.Models.ToDictionary(model => model.Name, model => model.Digest,
            StringComparer.OrdinalIgnoreCase);
    }

    public async Task<bool> IsInstalledAsync(
        VerifiedManifest manifest,
        string modelId,
        CancellationToken cancellationToken = default)
    {
        ValidateLocalApiUri();
        var model = manifest.Payload.Models.SingleOrDefault(candidate => candidate.Id == modelId)
            ?? throw new KeyNotFoundException($"El modelo {modelId} no está en el catálogo firmado.");
        var local = (await ReadTagsAsync(cancellationToken)).Models.FirstOrDefault(entry =>
            entry.Name.Equals(model.ModelTag, StringComparison.OrdinalIgnoreCase));
        if (local is null) return false;
        if (!DigestEquals(local.Digest, model.Digest))
            throw new InvalidDataException($"{model.ModelTag} ya existe en Ollama con un digest distinto; no se sobrescribió.");
        if (local.Size > model.MaximumDownloadBytes)
            throw new InvalidDataException($"El tamaño instalado de {model.ModelTag} excede el límite firmado.");
        return true;
    }

    private async Task<OllamaTagsResponse> ReadTagsAsync(CancellationToken cancellationToken)
    {
        using var response = await httpClient.GetAsync(ApiUri("api/tags"), cancellationToken);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<OllamaTagsResponse>(JsonOptions, cancellationToken)
            ?? throw new InvalidDataException("Ollama devolvió una respuesta vacía en /api/tags.");
    }

    private Uri ApiUri(string path) => new(apiBaseUri.AbsoluteUri.TrimEnd('/') + "/" + path);

    private void ValidateLocalApiUri()
    {
        if (!apiBaseUri.IsAbsoluteUri || apiBaseUri.Scheme is not ("http" or "https")
            || !string.IsNullOrEmpty(apiBaseUri.UserInfo)
            || !(apiBaseUri.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase)
                || (IPAddress.TryParse(apiBaseUri.Host, out var address) && IPAddress.IsLoopback(address))))
            throw new InvalidOperationException("La descarga solo puede dirigirse a un endpoint Ollama local.");
    }

    private static long? ReadLong(JsonElement root, string property) =>
        root.TryGetProperty(property, out var value) && value.TryGetInt64(out var number) ? number : null;

    private static bool DigestEquals(string? actual, string expected) =>
        NormalizeDigest(actual).Equals(NormalizeDigest(expected), StringComparison.OrdinalIgnoreCase);

    private static string NormalizeDigest(string? digest) =>
        (digest ?? "").StartsWith("sha256:", StringComparison.OrdinalIgnoreCase) ? digest![7..] : digest ?? "";

    private sealed record OllamaTagsResponse(IReadOnlyList<OllamaTag> Models);
    private sealed record OllamaTag(string Name, string Digest, long Size);
}
