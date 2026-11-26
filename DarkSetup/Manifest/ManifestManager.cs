using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace DarkSetup.Manifest;

public sealed record SignedManifestEnvelope(
    int SchemaVersion,
    string Algorithm,
    string PayloadBase64,
    string SignatureBase64);

public sealed record ManifestPayload(
    int SchemaVersion,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    IReadOnlyList<ManifestArtifact> Artifacts,
    IReadOnlyList<ManifestModel> Models,
    string? TermsVersion = null,
    string? TermsSha256 = null);

public sealed record ManifestArtifact(
    string Id,
    string Kind,
    string Version,
    string Architecture,
    string SourceUri,
    string RelativePath,
    long SizeBytes,
    string Sha256,
    string LicenseId,
    string LicenseUri,
    string? ModelId = null,
    ulong? EstimatedRamBytes = null,
    string InstallAction = "downloadOnly",
    string? InstallTargetPath = null,
    long? EstimatedInstalledBytes = null,
    bool Optional = false,
    string? DisplayName = null,
    string? Description = null,
    string? Publisher = null,
    IReadOnlyList<int>? AllowedExitCodes = null,
    IReadOnlyList<string>? DependsOn = null);

public sealed record ManifestModel(
    string Id,
    string Backend,
    string ModelTag,
    string Digest,
    long MaximumDownloadBytes,
    ulong EstimatedRamBytes,
    string Role,
    string SourceUri,
    string LicenseId,
    string LicenseUri);

public sealed class VerifiedManifest
{
    internal VerifiedManifest(ManifestPayload payload, string payloadSha256)
    {
        Payload = payload;
        PayloadSha256 = payloadSha256;
    }

    public ManifestPayload Payload { get; }
    public string PayloadSha256 { get; }
    public IReadOnlyList<ManifestArtifact> Artifacts => Payload.Artifacts;
}

public static partial class ManifestManager
{
    public const string SignatureAlgorithm = "ECDSA_P256_SHA256";
    private const int MaximumEnvelopeBytes = 8 * 1024 * 1024;
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = false,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        Converters = { new JsonStringEnumConverter() },
    };

    public static VerifiedManifest Verify(
        ReadOnlySpan<byte> envelopeBytes,
        string trustedPublicKeyPem,
        DateTimeOffset? now = null,
        IReadOnlySet<string>? allowedSourceHosts = null)
    {
        if (envelopeBytes.Length is 0 or > MaximumEnvelopeBytes)
            throw new InvalidDataException("El manifiesto firmado tiene un tamaño inválido.");
        SignedManifestEnvelope envelope;
        try
        {
            envelope = JsonSerializer.Deserialize<SignedManifestEnvelope>(envelopeBytes, JsonOptions)
                ?? throw new InvalidDataException("El manifiesto firmado está vacío.");
        }
        catch (JsonException error)
        {
            throw new InvalidDataException("El contenedor del manifiesto firmado no es válido.", error);
        }

        if (envelope.SchemaVersion != 1 || envelope.Algorithm != SignatureAlgorithm)
            throw new InvalidDataException("La versión o el algoritmo del manifiesto no están admitidos.");

        byte[] payloadBytes;
        byte[] signature;
        try
        {
            payloadBytes = Convert.FromBase64String(envelope.PayloadBase64);
            signature = Convert.FromBase64String(envelope.SignatureBase64);
        }
        catch (FormatException error)
        {
            throw new InvalidDataException("La carga o la firma del manifiesto no están codificadas correctamente.", error);
        }
        if (payloadBytes.Length is 0 or > MaximumEnvelopeBytes)
            throw new InvalidDataException("La carga del manifiesto tiene un tamaño inválido.");

        using var key = ECDsa.Create();
        try { key.ImportFromPem(trustedPublicKeyPem); }
        catch (Exception error) when (error is ArgumentException or CryptographicException)
        {
            throw new InvalidDataException("La clave pública de confianza no es válida.", error);
        }
        if (key.KeySize != 256)
            throw new InvalidDataException("La clave del manifiesto debe usar ECDSA P-256.");
        if (!key.VerifyData(payloadBytes, signature, HashAlgorithmName.SHA256, DSASignatureFormat.Rfc3279DerSequence))
            throw new CryptographicException("La firma del manifiesto no coincide con la clave de confianza.");

        ManifestPayload payload;
        try
        {
            payload = JsonSerializer.Deserialize<ManifestPayload>(payloadBytes, JsonOptions)
                ?? throw new InvalidDataException("La carga del manifiesto está vacía.");
        }
        catch (JsonException error)
        {
            throw new InvalidDataException("La carga del manifiesto no cumple el formato esperado.", error);
        }

        ValidatePayload(payload, now ?? DateTimeOffset.UtcNow, allowedSourceHosts);
        return new VerifiedManifest(payload,
            Convert.ToHexString(SHA256.HashData(payloadBytes)).ToLowerInvariant());
    }

    private static void ValidatePayload(ManifestPayload payload, DateTimeOffset now, IReadOnlySet<string>? allowedSourceHosts)
    {
        if (payload.SchemaVersion != 1)
            throw new InvalidDataException($"Versión de manifiesto no compatible: {payload.SchemaVersion}.");
        if (payload.IssuedAtUtc > now.AddMinutes(5) || payload.ExpiresAtUtc <= now
            || payload.ExpiresAtUtc <= payload.IssuedAtUtc)
            throw new InvalidDataException("El manifiesto aún no es válido o ya expiró.");
        if (payload.Artifacts is null || payload.Artifacts.Count > 1000)
            throw new InvalidDataException("El catálogo de artefactos supera el límite permitido.");
        if (payload.Models is null || payload.Models.Count > 500)
            throw new InvalidDataException("El catálogo de modelos supera el límite permitido.");
        if ((payload.TermsVersion is null) != (payload.TermsSha256 is null))
            throw new InvalidDataException("La versión y el SHA-256 de las condiciones deben declararse juntos.");
        if (payload.TermsVersion is { } termsVersion && (string.IsNullOrWhiteSpace(termsVersion)
            || termsVersion.Length > 128 || payload.TermsSha256 is not { Length: 64 } termsHash
            || !termsHash.All(Uri.IsHexDigit)))
            throw new InvalidDataException("La versión o el SHA-256 de las condiciones no son válidos.");
        if (payload.Artifacts.Count == 0 && payload.Models.Count == 0)
            throw new InvalidDataException("El manifiesto no contiene artefactos ni modelos.");

        var ids = new HashSet<string>(StringComparer.Ordinal);
        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        long maximumStorageBytes = 0;
        foreach (var artifact in payload.Artifacts)
        {
            if (!IdPattern().IsMatch(artifact.Id) || !ids.Add(artifact.Id))
                throw new InvalidDataException("El manifiesto contiene un identificador inválido o duplicado.");
            if (artifact.Kind is not ("runtime" or "model" or "voice" or "frontend" or "manager" or "dependency"))
                throw new InvalidDataException($"Tipo de artefacto no admitido: {artifact.Kind}.");
            if (string.IsNullOrWhiteSpace(artifact.Version) || artifact.Version.Length > 128
                || artifact.Architecture is not ("win-x64" or "any"))
                throw new InvalidDataException($"Versión o arquitectura inválida para {artifact.Id}.");
            if (artifact.SizeBytes <= 0 || artifact.SizeBytes > 1L << 50)
                throw new InvalidDataException($"Tamaño inválido para {artifact.Id}.");
            if (artifact.EstimatedInstalledBytes is < 0 or > 1L << 50)
                throw new InvalidDataException($"Tamaño instalado estimado inválido para {artifact.Id}.");
            try
            {
                maximumStorageBytes = checked(maximumStorageBytes + artifact.SizeBytes
                    + (artifact.EstimatedInstalledBytes ?? 0));
            }
            catch (OverflowException error)
            {
                throw new InvalidDataException("El espacio total requerido por el manifiesto excede el límite permitido.", error);
            }
            if (maximumStorageBytes > 1L << 50)
                throw new InvalidDataException("El espacio total requerido por el manifiesto excede el límite permitido.");
            if (string.IsNullOrWhiteSpace(artifact.DisplayName) || artifact.DisplayName.Length > 200)
                throw new InvalidDataException($"Nombre de visualización inválido para {artifact.Id}.");
            if (string.IsNullOrWhiteSpace(artifact.Description) || artifact.Description.Length > 1000)
                throw new InvalidDataException($"Descripción de instalación inválida para {artifact.Id}.");
            if (string.IsNullOrWhiteSpace(artifact.Publisher) || artifact.Publisher.Length > 200)
                throw new InvalidDataException($"Editor no verificado para {artifact.Id}.");
            if (artifact.AllowedExitCodes is null || artifact.AllowedExitCodes.Count > 32
                || artifact.AllowedExitCodes.Any(code => code is < 0 or > 65535)
                || artifact.AllowedExitCodes.Distinct().Count() != artifact.AllowedExitCodes.Count)
                throw new InvalidDataException($"Códigos de salida inválidos para {artifact.Id}.");
            if (artifact.DependsOn is null || artifact.DependsOn.Count > 100
                || artifact.DependsOn.Any(dependency => !IdPattern().IsMatch(dependency) || dependency == artifact.Id)
                || artifact.DependsOn.Distinct(StringComparer.Ordinal).Count() != artifact.DependsOn.Count)
                throw new InvalidDataException($"Dependencias inválidas para {artifact.Id}.");
            if (!Sha256Pattern().IsMatch(artifact.Sha256))
                throw new InvalidDataException($"SHA-256 inválido para {artifact.Id}.");
            if (!IsHttpsUri(artifact.SourceUri) || !IsAllowedSource(artifact.SourceUri, allowedSourceHosts) || !IsHttpsUri(artifact.LicenseUri)
                || string.IsNullOrWhiteSpace(artifact.LicenseId) || artifact.LicenseId.Length > 128)
                throw new InvalidDataException($"Origen o licencia no verificados para {artifact.Id}.");
            if (artifact.Kind == "model" && (string.IsNullOrWhiteSpace(artifact.ModelId)
                || artifact.ModelId.Length > 256 || artifact.EstimatedRamBytes is null or 0))
                throw new InvalidDataException($"El modelo {artifact.Id} requiere ModelId y memoria estimada.");
            if (!IsSafeRelativePath(artifact.RelativePath)
                || !paths.Add(artifact.RelativePath.Replace('\\', '/')))
                throw new InvalidDataException($"Ruta de instalación inválida o duplicada para {artifact.Id}.");
            if (artifact.InstallAction is not ("downloadOnly" or "extractZip" or "runInstaller"))
                throw new InvalidDataException($"Acción de instalación no admitida para {artifact.Id}.");
            if (artifact.InstallAction == "extractZip"
                && (!artifact.RelativePath.EndsWith(".zip", StringComparison.OrdinalIgnoreCase)
                    || !IsSafeInstallTargetPath(artifact.InstallTargetPath ?? "")
                    || artifact.EstimatedInstalledBytes is null or <= 0))
                throw new InvalidDataException($"El ZIP {artifact.Id} requiere ruta de extracción y tamaño instalado estimado.");
            if (artifact.InstallAction == "runInstaller"
                && (!artifact.RelativePath.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
                    || artifact.EstimatedInstalledBytes is null or <= 0
                    || !artifact.AllowedExitCodes!.Contains(0)))
                throw new InvalidDataException($"El instalador ejecutable {artifact.Id} debe ser .exe, indicar el tamaño instalado estimado y admitir salida 0.");
            if (artifact.InstallAction != "runInstaller" && artifact.AllowedExitCodes!.Count != 0)
                throw new InvalidDataException($"La acción {artifact.InstallAction} no admite códigos de salida para {artifact.Id}.");
        }

        ValidateArtifactDependencies(payload.Artifacts);

        var modelIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (var model in payload.Models)
        {
            if (!IdPattern().IsMatch(model.Id) || !modelIds.Add(model.Id)
                || model.Backend != "ollama" || !ModelTagPattern().IsMatch(model.ModelTag))
                throw new InvalidDataException("El catálogo contiene un modelo con identificador/backend inválido o duplicado.");
            if (model.MaximumDownloadBytes <= 0 || model.MaximumDownloadBytes > 1L << 50
                || model.EstimatedRamBytes == 0 || model.EstimatedRamBytes > 1UL << 50)
                throw new InvalidDataException($"Límites de almacenamiento/memoria inválidos para el modelo {model.Id}.");
            if (!DigestPattern().IsMatch(model.Digest)
                || model.Role is not ("chat" or "nucleus" or "coder")
                || !IsHttpsUri(model.SourceUri) || !IsAllowedSource(model.SourceUri, allowedSourceHosts) || !IsHttpsUri(model.LicenseUri)
                || string.IsNullOrWhiteSpace(model.LicenseId) || model.LicenseId.Length > 128)
                throw new InvalidDataException($"Digest, función, origen o licencia inválidos para el modelo {model.Id}.");
        }
    }

    private static void ValidateArtifactDependencies(IReadOnlyList<ManifestArtifact> artifacts)
    {
        var byId = artifacts.ToDictionary(artifact => artifact.Id, StringComparer.Ordinal);
        foreach (var artifact in artifacts)
            foreach (var dependency in artifact.DependsOn!)
                if (!byId.ContainsKey(dependency))
                    throw new InvalidDataException($"La dependencia {dependency} de {artifact.Id} no existe en el manifiesto.");

        var visited = new HashSet<string>(StringComparer.Ordinal);
        var active = new HashSet<string>(StringComparer.Ordinal);
        void Visit(string id)
        {
            if (visited.Contains(id)) return;
            if (!active.Add(id)) throw new InvalidDataException("Las dependencias de artefactos contienen un ciclo.");
            foreach (var dependency in byId[id].DependsOn!) Visit(dependency);
            active.Remove(id);
            visited.Add(id);
        }
        foreach (var id in byId.Keys) Visit(id);
    }

    private static bool IsHttpsUri(string value) =>
        Uri.TryCreate(value, UriKind.Absolute, out var uri)
        && uri.Scheme == Uri.UriSchemeHttps
        && string.IsNullOrEmpty(uri.UserInfo)
        && string.IsNullOrEmpty(uri.Fragment);

    private static bool IsAllowedSource(string value, IReadOnlySet<string>? allowedHosts) =>
        allowedHosts is not null && Uri.TryCreate(value, UriKind.Absolute, out var uri)
        && allowedHosts.Contains(uri.IdnHost);

    private static bool IsSafeRelativePath(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || path.Length > 512 || Path.IsPathRooted(path)
            || path.Contains(':') || path.Contains('\0')) return false;
        var parts = path.Replace('\\', '/').Split('/');
        return parts.All(part => part.Length > 0 && part is not ("." or ".."));
    }

    private static bool IsSafeInstallTargetPath(string path) =>
        path == "." || IsSafeRelativePath(path);

    [GeneratedRegex("^[a-z0-9][a-z0-9._-]{0,127}$", RegexOptions.CultureInvariant)]
    private static partial Regex IdPattern();

    [GeneratedRegex("^[a-fA-F0-9]{64}$", RegexOptions.CultureInvariant)]
    private static partial Regex Sha256Pattern();

    [GeneratedRegex("^sha256:[a-fA-F0-9]{64}$", RegexOptions.CultureInvariant)]
    private static partial Regex DigestPattern();

    [GeneratedRegex("^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$", RegexOptions.CultureInvariant)]
    private static partial Regex ModelTagPattern();
}
