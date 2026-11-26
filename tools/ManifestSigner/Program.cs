using System.Security.Cryptography;
using System.Text.Json;
using DarkSetup.Manifest;

if (args.Length == 3 && args[0] == "keygen")
    return GenerateKeyPair(args[1], args[2]);

if (args.Length != 4 || args[0] != "sign")
{
    Console.Error.WriteLine("Uso:");
    Console.Error.WriteLine("  ManifestSigner keygen <clave-privada.pem> <clave-publica.pem>");
    Console.Error.WriteLine("  ManifestSigner sign <payload.json> <clave-privada.pem> <manifiesto-firmado.json>");
    return 2;
}

var payloadPath = Path.GetFullPath(args[1]);
var privateKeyPath = Path.GetFullPath(args[2]);
var outputPath = Path.GetFullPath(args[3]);
if (outputPath.Equals(privateKeyPath, StringComparison.OrdinalIgnoreCase)
    || outputPath.Equals(payloadPath, StringComparison.OrdinalIgnoreCase))
{
    Console.Error.WriteLine("El archivo de salida no puede reemplazar el payload ni la clave privada.");
    return 2;
}

try
{
    var payloadBytes = await File.ReadAllBytesAsync(payloadPath);
    if (payloadBytes.Length is 0 or > 8 * 1024 * 1024)
        throw new InvalidDataException("El payload supera el tamaño admitido.");

    using var key = ECDsa.Create();
    key.ImportFromPem(await File.ReadAllTextAsync(privateKeyPath));
    if (key.KeySize != 256)
        throw new InvalidDataException("La clave de firma debe ser ECDSA P-256.");

    var signature = key.SignData(payloadBytes, HashAlgorithmName.SHA256,
        DSASignatureFormat.Rfc3279DerSequence);
    var envelopeBytes = JsonSerializer.SerializeToUtf8Bytes(new SignedManifestEnvelope(
        1,
        ManifestManager.SignatureAlgorithm,
        Convert.ToBase64String(payloadBytes),
        Convert.ToBase64String(signature)), new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        });

    var verified = ManifestManager.Verify(envelopeBytes, key.ExportSubjectPublicKeyInfoPem());
    var directory = Path.GetDirectoryName(outputPath)
        ?? throw new InvalidOperationException("La salida debe tener una carpeta destino.");
    Directory.CreateDirectory(directory);
    var temporaryPath = outputPath + ".tmp";
    try
    {
        await File.WriteAllBytesAsync(temporaryPath, envelopeBytes);
        File.Move(temporaryPath, outputPath, overwrite: true);
    }
    finally
    {
        if (File.Exists(temporaryPath)) File.Delete(temporaryPath);
    }

    Console.WriteLine($"Manifiesto firmado y verificado: {outputPath}");
    Console.WriteLine($"Payload SHA-256: {verified.PayloadSha256}");
    Console.WriteLine("Clave pública para fijar en el verificador:");
    Console.WriteLine(key.ExportSubjectPublicKeyInfoPem());
    return 0;
}
catch (Exception error) when (error is IOException or UnauthorizedAccessException
    or CryptographicException or ArgumentException or InvalidDataException or JsonException)
{
    Console.Error.WriteLine($"No se pudo firmar el manifiesto: {error.Message}");
    return 1;
}

static int GenerateKeyPair(string privateKeyArgument, string publicKeyArgument)
{
    var privateKeyPath = Path.GetFullPath(privateKeyArgument);
    var publicKeyPath = Path.GetFullPath(publicKeyArgument);
    if (privateKeyPath.Equals(publicKeyPath, StringComparison.OrdinalIgnoreCase))
    {
        Console.Error.WriteLine("La clave privada y la pública deben tener rutas distintas.");
        return 2;
    }

    var privateCreated = false;
    var publicCreated = false;
    try
    {
        using var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
        var privatePem = key.ExportPkcs8PrivateKeyPem();
        var publicPem = key.ExportSubjectPublicKeyInfoPem();
        WriteNewPem(privateKeyPath, privatePem);
        privateCreated = true;
        WriteNewPem(publicKeyPath, publicPem);
        publicCreated = true;
        Console.WriteLine($"Clave ECDSA P-256 creada fuera del proyecto: {privateKeyPath}");
        Console.WriteLine($"Clave pública: {publicKeyPath}");
        return 0;
    }
    catch (Exception error) when (error is IOException or UnauthorizedAccessException
        or CryptographicException or ArgumentException)
    {
        if (privateCreated) File.Delete(privateKeyPath);
        if (publicCreated) File.Delete(publicKeyPath);
        Console.Error.WriteLine($"No se pudo crear el par de claves: {error.Message}");
        return 1;
    }
}

static void WriteNewPem(string path, string pem)
{
    var directory = Path.GetDirectoryName(path)
        ?? throw new InvalidOperationException("La clave debe tener una carpeta destino.");
    if (!Directory.Exists(directory)) throw new DirectoryNotFoundException("La carpeta de la clave debe existir y estar protegida.");
    using var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None,
        4096, FileOptions.WriteThrough);
    var bytes = System.Text.Encoding.UTF8.GetBytes(pem);
    stream.Write(bytes);
    stream.Flush(flushToDisk: true);
}
