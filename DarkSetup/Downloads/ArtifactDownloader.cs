using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using DarkSetup.Manifest;

namespace DarkSetup.Downloads;

public sealed record DownloadProgress(string ArtifactId, long BytesDownloaded, long TotalBytes);

public sealed class ArtifactDownloader : IDisposable
{
    private readonly HttpClient _http;
    private readonly bool _ownsClient;
    private readonly IReadOnlySet<string> _allowedHosts;
    private readonly string? _localBundleRoot;

    public ArtifactDownloader(HttpClient? httpClient = null, IReadOnlySet<string>? allowedHosts = null,
        string? localBundleRoot = null)
    {
        _http = httpClient ?? new HttpClient(new HttpClientHandler { AllowAutoRedirect = false });
        _ownsClient = httpClient is null;
        _allowedHosts = allowedHosts ?? new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        _localBundleRoot = localBundleRoot is null ? null : Path.GetFullPath(localBundleRoot);
    }

    public async Task<string> DownloadAsync(
        VerifiedManifest manifest,
        string artifactId,
        string installationRoot,
        IProgress<DownloadProgress>? progress = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(manifest);
        var artifact = manifest.Artifacts.SingleOrDefault(item => item.Id == artifactId)
            ?? throw new KeyNotFoundException($"El artefacto {artifactId} no está en el manifiesto verificado.");
        var root = Path.GetFullPath(installationRoot);
        var destination = ResolveContainedPath(root, artifact.RelativePath);
        var partial = destination + ".partial";
        EnsureNoReparsePointParents(root, destination);
        EnsureNotReparsePoint(destination);
        EnsureNotReparsePoint(partial);
        Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
        EnsureNoReparsePointParents(root, destination);

        if (File.Exists(destination) && await MatchesAsync(destination, artifact, cancellationToken))
        {
            progress?.Report(new DownloadProgress(artifact.Id, artifact.SizeBytes, artifact.SizeBytes));
            return destination;
        }

        var offset = File.Exists(partial) ? new FileInfo(partial).Length : 0;
        if (offset > artifact.SizeBytes)
        {
            File.Delete(partial);
            offset = 0;
        }
        if (offset == artifact.SizeBytes)
        {
            if (await MatchesAsync(partial, artifact, cancellationToken))
            {
                File.Move(partial, destination, overwrite: true);
                progress?.Report(new DownloadProgress(artifact.Id, artifact.SizeBytes, artifact.SizeBytes));
                return destination;
            }
            File.Delete(partial);
            offset = 0;
        }

        var rootDrive = Path.GetPathRoot(root);
        if (string.IsNullOrEmpty(rootDrive) || new DriveInfo(rootDrive).AvailableFreeSpace < artifact.SizeBytes - offset)
            throw new IOException($"No hay espacio libre suficiente para descargar {artifact.Id}.");

        if (_localBundleRoot is not null)
        {
            await CopyFromLocalBundleAsync(artifact, partial, destination, offset, progress, cancellationToken);
            return destination;
        }

        using var response = await SendAsync(new Uri(artifact.SourceUri), offset, cancellationToken);
        response.EnsureSuccessStatusCode();
        var append = offset > 0 && response.StatusCode == HttpStatusCode.PartialContent
            && response.Content.Headers.ContentRange?.From == offset;
        if (response.StatusCode == HttpStatusCode.PartialContent
            && response.Content.Headers.ContentRange?.From != (append ? offset : 0))
            throw new InvalidDataException("El servidor devolvió un rango que no coincide con el archivo parcial.");
        if (response.StatusCode != HttpStatusCode.OK && response.StatusCode != HttpStatusCode.PartialContent)
            throw new InvalidDataException($"Respuesta de descarga inesperada: {(int)response.StatusCode}.");
        var finalUri = response.RequestMessage?.RequestUri;
        if (finalUri is null || finalUri.Scheme != Uri.UriSchemeHttps
            || !string.IsNullOrEmpty(finalUri.UserInfo) || !_allowedHosts.Contains(finalUri.IdnHost))
            throw new InvalidDataException("La respuesta final de descarga no procede de un host HTTPS autorizado.");

        var initialBytes = append ? offset : 0;
        await using (var output = new FileStream(partial,
            append ? FileMode.Append : FileMode.Create,
            FileAccess.Write, FileShare.None, 128 * 1024,
            FileOptions.Asynchronous | FileOptions.SequentialScan))
        await using (var input = await response.Content.ReadAsStreamAsync(cancellationToken))
        {
            var buffer = new byte[128 * 1024];
            var total = initialBytes;
            int read;
            while ((read = await input.ReadAsync(buffer, cancellationToken)) > 0)
            {
                if (total + read > artifact.SizeBytes)
                    throw new InvalidDataException($"La descarga de {artifact.Id} supera el tamaño firmado.");
                await output.WriteAsync(buffer.AsMemory(0, read), cancellationToken);
                total += read;
                progress?.Report(new DownloadProgress(artifact.Id, total, artifact.SizeBytes));
            }
            await output.FlushAsync(cancellationToken);
        }

        if (new FileInfo(partial).Length != artifact.SizeBytes)
            throw new EndOfStreamException($"La descarga de {artifact.Id} quedó incompleta; puede reanudarse.");
        if (!await MatchesAsync(partial, artifact, cancellationToken))
        {
            File.Delete(partial);
            throw new CryptographicException($"El SHA-256 de {artifact.Id} no coincide con el manifiesto.");
        }
        File.Move(partial, destination, overwrite: true);
        return destination;
    }

    private async Task CopyFromLocalBundleAsync(ManifestArtifact artifact, string partial, string destination,
        long offset, IProgress<DownloadProgress>? progress, CancellationToken cancellationToken)
    {
        var sourceUri = new Uri(artifact.SourceUri);
        if (sourceUri.Scheme != Uri.UriSchemeHttps || sourceUri.IdnHost != "tester-bundle.dark.invalid"
            || !_allowedHosts.Contains(sourceUri.IdnHost))
            throw new InvalidDataException("El bundle local solo admite el origen reservado para builds Tester.");
        var source = ResolveContainedPath(_localBundleRoot!, artifact.RelativePath);
        EnsureNoReparsePointParents(_localBundleRoot!, source);
        EnsureNotReparsePoint(source);
        if (!File.Exists(source) || new FileInfo(source).Length != artifact.SizeBytes)
            throw new FileNotFoundException("Falta el payload local o su tamaño no coincide con el manifiesto firmado.", source);

        await using (var sourceStream = new FileStream(source, FileMode.Open, FileAccess.Read, FileShare.Read,
            128 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan))
        {
            var sourceDigest = await SHA256.HashDataAsync(sourceStream, cancellationToken);
            if (!CryptographicOperations.FixedTimeEquals(sourceDigest, Convert.FromHexString(artifact.Sha256)))
                throw new CryptographicException($"El SHA-256 del payload local {artifact.Id} no coincide con el manifiesto firmado.");
        }

        // Los flujos se cierran ANTES de verificar y mover: si el .partial sigue abierto para
        // escritura, MatchesAsync no puede leerlo ("el archivo esta siendo utilizado por otro proceso").
        var copied = offset;
        await using (var input = new FileStream(source, FileMode.Open, FileAccess.Read, FileShare.Read,
            128 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan))
        await using (var output = new FileStream(partial, offset > 0 ? FileMode.Append : FileMode.Create,
            FileAccess.Write, FileShare.None, 128 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan))
        {
            if (offset > 0) input.Seek(offset, SeekOrigin.Begin);
            var buffer = new byte[128 * 1024];
            int read;
            while ((read = await input.ReadAsync(buffer, cancellationToken)) > 0)
            {
                await output.WriteAsync(buffer.AsMemory(0, read), cancellationToken);
                copied += read;
                progress?.Report(new DownloadProgress(artifact.Id, copied, artifact.SizeBytes));
            }
            await output.FlushAsync(cancellationToken);
        }
        if (copied != artifact.SizeBytes || !await MatchesAsync(partial, artifact, cancellationToken))
        {
            File.Delete(partial);
            throw new CryptographicException($"La copia local de {artifact.Id} no coincide con el manifiesto firmado.");
        }
        File.Move(partial, destination, overwrite: true);
    }

    private async Task<HttpResponseMessage> SendAsync(Uri source, long offset, CancellationToken cancellationToken)
    {
        var current = source;
        for (var redirects = 0; redirects <= 5; redirects++)
        {
            if (current.Scheme != Uri.UriSchemeHttps || !string.IsNullOrEmpty(current.UserInfo)
                || !_allowedHosts.Contains(current.IdnHost))
                throw new InvalidDataException("La URL de descarga o su redirección no es HTTPS.");
            using var request = new HttpRequestMessage(HttpMethod.Get, current);
            if (offset > 0) request.Headers.Range = new RangeHeaderValue(offset, null);
            var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
            if ((int)response.StatusCode is >= 300 and < 400)
            {
                var location = response.Headers.Location;
                response.Dispose();
                if (location is null || redirects == 5)
                    throw new HttpRequestException("La descarga excedió el límite de redirecciones.");
                current = location.IsAbsoluteUri ? location : new Uri(current, location);
                if (current.Scheme != Uri.UriSchemeHttps || !_allowedHosts.Contains(current.IdnHost))
                    throw new InvalidDataException("La redirección apunta a un host HTTPS no aprobado.");
                continue;
            }
            return response;
        }
        throw new HttpRequestException("La descarga excedió el límite de redirecciones.");
    }

    private static async Task<bool> MatchesAsync(string path, ManifestArtifact artifact, CancellationToken cancellationToken)
    {
        if (!File.Exists(path) || new FileInfo(path).Length != artifact.SizeBytes) return false;
        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read,
            128 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan);
        var digest = await SHA256.HashDataAsync(stream, cancellationToken);
        return CryptographicOperations.FixedTimeEquals(digest, Convert.FromHexString(artifact.Sha256));
    }

    private static string ResolveContainedPath(string root, string relativePath)
    {
        var destination = Path.GetFullPath(Path.Combine(root, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        var rootPrefix = Path.EndsInDirectorySeparator(root) ? root : root + Path.DirectorySeparatorChar;
        if (!destination.StartsWith(rootPrefix, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("La ruta del artefacto sale del directorio de instalación.");
        return destination;
    }

    private static void EnsureNoReparsePointParents(string root, string destination)
    {
        if (Directory.Exists(root) && (File.GetAttributes(root) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("El directorio de instalación es un punto de reanálisis.");
        var relativeParent = Path.GetRelativePath(root, Path.GetDirectoryName(destination)!);
        var current = root;
        foreach (var part in relativeParent.Split(Path.DirectorySeparatorChar, StringSplitOptions.RemoveEmptyEntries))
        {
            current = Path.Combine(current, part);
            if (Directory.Exists(current)
                && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("La ruta de instalación atraviesa un punto de reanálisis.");
        }
    }

    private static void EnsureNotReparsePoint(string path)
    {
        if (File.Exists(path) && (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("El archivo destino es un punto de reanálisis.");
    }

    public void Dispose()
    {
        if (_ownsClient) _http.Dispose();
    }
}
