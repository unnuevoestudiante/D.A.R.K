using System.Text.Json;
using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.IO.Compression;
using DarkSetup.Hardware;
using DarkSetup.Downloads;
using DarkSetup.Manifest;
using DarkSetup.Models;
using DarkSetup.Provisioning;

var failures = new List<string>();
var testSourceHosts = new HashSet<string>(["downloads.example.test", "ollama.com"], StringComparer.OrdinalIgnoreCase);
var temporaryRoot = Path.Combine(Path.GetTempPath(), "dark-setup-validation-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(temporaryRoot);

void Check(bool condition, string description)
{
    Console.WriteLine($"{(condition ? "PASS" : "FAIL")} {description}");
    if (!condition) failures.Add(description);
}

async Task<T> ThrowsAsync<T>(Func<Task> action) where T : Exception
{
    try { await action(); }
    catch (T error) { return error; }
    throw new InvalidOperationException($"Expected {typeof(T).Name} was not thrown.");
}

Dictionary<string, string> ChoicesFrom(ModelProfileSelection selection) =>
    selection.Models.ToDictionary(model => model.Role, model => model.ManifestModelId, StringComparer.Ordinal);

try
{
    using (var retryCancellation = new DarkSetup.RetryableCancellation())
    {
        var firstRunToken = retryCancellation.BeginRun();
        retryCancellation.Cancel();
        Check(firstRunToken.IsCancellationRequested, "el cancelador detiene la ejecución actual");
        retryCancellation.EndRun();
        var retryToken = retryCancellation.BeginRun();
        Check(!retryToken.IsCancellationRequested, "una nueva ejecución obtiene un token no cancelado tras cancelar la anterior");
        retryCancellation.EndRun();
    }
    Check(DarkSetup.InstallerExitCode.IsAccepted(3010) && DarkSetup.InstallerExitCode.RequiresRestart(3010)
        && DarkSetup.InstallerExitCode.IsAccepted(0) && !DarkSetup.InstallerExitCode.RequiresRestart(0)
        && !DarkSetup.InstallerExitCode.IsAccepted(1),
        "runInstaller acepta 3010 como reinicio pendiente y rechaza códigos no admitidos");
    const ulong gib = 1024UL * 1024 * 1024;
    Check(HardwareProbe.Classify(11 * gib, null) == "limited", "perfil limitado por debajo de 12 GiB RAM");
    Check(HardwareProbe.Classify(12 * gib, null) == "standard", "perfil estándar desde 12 GiB RAM");
    Check(HardwareProbe.Classify(32 * gib, null) == "high", "perfil alto desde 32 GiB RAM");
    Check(HardwareProbe.Classify(16 * gib, 8 * gib) == "high", "perfil alto por VRAM aunque la RAM sea estándar");
    Check(HardwareProbe.Classify(64 * gib, 24 * gib) == "station", "perfil estación por RAM y VRAM");
    Check(HardwareProbe.Classify(64 * gib, null) == "high", "VRAM desconocida no se interpreta como estación");

    var repositoryRoot = new DirectoryInfo(AppContext.BaseDirectory);
    while (repositoryRoot is not null && !File.Exists(Path.Combine(repositoryRoot.FullName, "config", "model-profiles.json")))
        repositoryRoot = repositoryRoot.Parent;
    if (repositoryRoot is null) throw new DirectoryNotFoundException("No se encontró la raíz del proyecto para validar perfiles.");
    var profileCatalogPath = Path.Combine(repositoryRoot.FullName, "config", "model-profiles.json");
    var managerRegistryPath = Path.Combine(repositoryRoot.FullName, "DarkManager", "DarkManager", "models.json");
    HardwareProbeResult Hardware(ulong? ramBytes, ulong? vramBytes)
    {
        var profile = HardwareProbe.Classify(ramBytes, vramBytes);
        return new HardwareProbeResult(1, DateTimeOffset.UtcNow,
            new OperatingSystemInfo("Windows", "11", "22631", "X64", true),
            new CpuInfo("validation", 8, 16), new MemoryInfo(ramBytes, ramBytes), [],
            new StorageInfo("C:\\", "C:\\", 100_000_000_000), profile, []);
    }

    var limitedModels = ModelProfileSelector.Select(Hardware(8 * gib, null), profileCatalogPath, managerRegistryPath);
    Check(limitedModels.SelectedProfile == "limited"
        && limitedModels.Models.Select(model => model.ModelTag).SequenceEqual([
            "qwen3:0.6b-q4_K_M", "qwen2.5:0.5b-instruct-q4_K_M", "qwen2.5-coder:0.5b-instruct-q4_K_M"]),
        "perfil limitado selecciona equivalentes compactos de chat, núcleo y código");
    var standardModels = ModelProfileSelector.Select(Hardware(16 * gib, null), profileCatalogPath, managerRegistryPath);
    Check(standardModels.SelectedProfile == "standard"
        && standardModels.Models.Select(model => model.ModelTag).SequenceEqual([
            "qwen3:4b-instruct-2507-q8_0", "qwen2.5:7b-instruct", "qwen2.5-coder:7b"])
        && standardModels.Models.Select(model => model.EstimatedRamMB).SequenceEqual([4500, 5000, 5000]),
        "perfil estándar toma modelos, memorias y prioridades directamente de DarkManager");
    Check(standardModels.Models[0].ModelTag == "qwen3:4b-instruct-2507-q8_0",
        "el modelo chat de runtime.json coincide con el estándar de DarkManager");
    var standardLowDiskHardware = Hardware(16 * gib, null) with
    {
        TargetStorage = new StorageInfo("C:\\", "C:\\", 4 * 1024L * 1024 * 1024),
    };
    var standardLowDisk = ModelProfileSelector.Select(standardLowDiskHardware, profileCatalogPath, managerRegistryPath);
    Check(standardLowDisk.SelectedProfile == "standard" && !standardLowDisk.FitsStorage
        && standardLowDisk.EstimatedProfileStorageMB == 13_700,
        "el perfil elegido informa si falta espacio para instalar todos los modelos estimados");
    var highModels = ModelProfileSelector.Select(Hardware(40 * gib, null), profileCatalogPath, managerRegistryPath);
    Check(highModels.SelectedProfile == "high"
        && highModels.Models.All(model => model.ModelTag.Contains("14b", StringComparison.Ordinal)),
        "perfil alto selecciona equivalentes Q4_K_M de 14B");
    var stationModels = ModelProfileSelector.Select(Hardware(64 * gib, 24 * gib), profileCatalogPath, managerRegistryPath);
    Check(stationModels.SelectedProfile == "station"
        && stationModels.Models.All(model => model.ModelTag.Contains("32b", StringComparison.Ordinal)),
        "perfil estación selecciona equivalentes Q4_K_M de 32B");
    var vramOnlyHigh = ModelProfileSelector.Select(Hardware(16 * gib, 8 * gib), profileCatalogPath, managerRegistryPath);
    Check(vramOnlyHigh.HardwareProfile == "high" && vramOnlyHigh.SelectedProfile == "standard",
        "el presupuesto RAM degrada con seguridad un perfil alto determinado solo por VRAM");
    var smallHighMemory = ModelProfileSelector.Select(Hardware(8 * gib, 8 * gib), profileCatalogPath, managerRegistryPath);
    Check(smallHighMemory.HardwareProfile == "high" && smallHighMemory.SelectedProfile == "limited",
        "un perfil alto por VRAM usa modelos limitados si la RAM no sostiene los estándar");
    var tunedBudget = ModelProfileSelector.Select(Hardware(16 * gib, null), profileCatalogPath, managerRegistryPath, 0.4);
    Check(tunedBudget.ManagerMemoryBudgetMB == (long)(16d * 1024 * 0.4), "el presupuesto de memoria usa la proporción de configuración");

    var engine = new ProvisioningEngine();
    var installed = new HashSet<string>(StringComparer.Ordinal);
    var baseRuns = 0;
    var featureRuns = 0;
    var orderedSteps = new[]
    {
        new ProvisioningStep
        {
            Id = "feature",
            DependsOn = ["base"],
            ExecuteAsync = _ => { featureRuns++; installed.Add("feature"); return Task.CompletedTask; },
            VerifyAsync = _ => Task.FromResult(installed.Contains("feature")),
        },
        new ProvisioningStep
        {
            Id = "base",
            ExecuteAsync = _ => { baseRuns++; installed.Add("base"); return Task.CompletedTask; },
            VerifyAsync = _ => Task.FromResult(installed.Contains("base")),
        },
    };
    var journalPath = Path.Combine(temporaryRoot, "graph", "state.json");
    var firstRun = await engine.RunAsync(orderedSteps, journalPath);
    Check(firstRun.All(item => item.Status == ProvisioningStepStatus.Succeeded), "grafo dependiente completa y verifica los pasos");
    Check(baseRuns == 1 && featureRuns == 1, "el grafo respeta el orden topológico aunque los pasos lleguen invertidos");
    var resumed = await engine.RunAsync(orderedSteps, journalPath);
    Check(resumed.All(item => item.Status == ProvisioningStepStatus.Succeeded) && baseRuns == 1 && featureRuns == 1,
        "la reanudación re-verifica y omite pasos ya completados");
    var changedSelection = await engine.RunAsync([orderedSteps[1]], journalPath);
    Check(changedSelection.Count == 1 && changedSelection[0].Id == "base"
        && JsonDocument.Parse(await File.ReadAllTextAsync(journalPath)).RootElement.GetProperty("Steps").EnumerateObject().Count() == 1,
        "la reanudación admite pasos añadidos o retirados conservando los pasos coincidentes");
    Check(File.Exists(journalPath) && JsonDocument.Parse(await File.ReadAllTextAsync(journalPath)).RootElement
        .GetProperty("Steps").EnumerateObject().Count() == 1 && baseRuns == 1
        && changedSelection.Single().Status == ProvisioningStepStatus.Succeeded,
        "el journal conserva el estado coincidente y retira el paso deseleccionado");

    var canceledPath = Path.Combine(temporaryRoot, "cancel", "state.json");
    using (var cancel = new CancellationTokenSource(TimeSpan.FromMilliseconds(80)))
    {
        await ThrowsAsync<OperationCanceledException>(() => engine.RunAsync([
            new ProvisioningStep
            {
                Id = "download-like",
                ExecuteAsync = async token => await Task.Delay(TimeSpan.FromSeconds(5), token),
                VerifyAsync = _ => Task.FromResult(false),
            },
        ], canceledPath, cancel.Token));
    }
    var canceledState = JsonDocument.Parse(await File.ReadAllTextAsync(canceledPath)).RootElement
        .GetProperty("Steps").GetProperty("download-like").GetProperty("Status").GetString();
    Check(canceledState == "Interrupted", "la cancelación conserva estado interrumpido en el journal");
    var recovered = false;
    var recoveryRuns = 0;
    var recoveredState = await engine.RunAsync([
        new ProvisioningStep
        {
            Id = "download-like",
            ExecuteAsync = _ => throw new InvalidOperationException("no debe repetir el paso recuperable"),
            VerifyAsync = _ => Task.FromResult(recovered),
            RecoverAsync = _ => { recoveryRuns++; recovered = true; return Task.CompletedTask; },
        },
    ], canceledPath);
    Check(recoveryRuns == 1 && recoveredState.Single().Status == ProvisioningStepStatus.Succeeded,
        "la reanudación recupera y verifica un paso cancelado antes de repetirlo");

    var failPath = Path.Combine(temporaryRoot, "failure", "state.json");
    var blockedRuns = 0;
    var failureState = await engine.RunAsync([
        new ProvisioningStep
        {
            Id = "required",
            ExecuteAsync = _ => throw new ProvisioningException("component_missing", "Componente obligatorio ausente."),
            VerifyAsync = _ => Task.FromResult(false),
        },
        new ProvisioningStep
        {
            Id = "dependent",
            DependsOn = ["required"],
            ExecuteAsync = _ => { blockedRuns++; return Task.CompletedTask; },
            VerifyAsync = _ => Task.FromResult(false),
        },
    ], failPath);
    Check(failureState.Single(item => item.Id == "required").Status == ProvisioningStepStatus.Failed
        && failureState.Single(item => item.Id == "dependent").Status == ProvisioningStepStatus.Blocked
        && blockedRuns == 0, "un fallo de un paso bloquea dependencias sin ejecutarlas");

    var cyclePath = Path.Combine(temporaryRoot, "cycle.json");
    await ThrowsAsync<ArgumentException>(() => engine.RunAsync([
        new ProvisioningStep { Id = "a", DependsOn = ["b"], ExecuteAsync = _ => Task.CompletedTask, VerifyAsync = _ => Task.FromResult(false) },
        new ProvisioningStep { Id = "b", DependsOn = ["a"], ExecuteAsync = _ => Task.CompletedTask, VerifyAsync = _ => Task.FromResult(false) },
    ], cyclePath));
    Check(!File.Exists(cyclePath), "el ciclo se rechaza antes de escribir un journal o ejecutar pasos");

    using var signingKey = ECDsa.Create(ECCurve.NamedCurves.nistP256);
    var now = DateTimeOffset.UtcNow;
    var bytes = Encoding.UTF8.GetBytes("dark-artifact");
    var digest = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    var artifact = new
    {
        id = "sample-runtime",
        kind = "runtime",
        displayName = "D.A.R.K. Python Runtime",
        description = "Intérprete de Python que ejecuta los servicios de D.A.R.K.",
        version = "1.0.0",
        architecture = "win-x64",
        sourceUri = "https://downloads.example.test/sample.bin",
        relativePath = "runtime/sample.bin",
        sizeBytes = bytes.Length,
        sha256 = digest,
        licenseId = "MIT",
        licenseUri = "https://opensource.org/license/mit",
        publisher = "D.A.R.K. Validation",
        allowedExitCodes = Array.Empty<int>(),
        dependsOn = Array.Empty<string>(),
    };
    var signedPayload = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1,
        issuedAtUtc = now.AddMinutes(-1),
        expiresAtUtc = now.AddHours(2),
        artifacts = new[] { artifact },
        models = Array.Empty<object>(),
    });
    var signature = signingKey.SignData(signedPayload, HashAlgorithmName.SHA256,
        DSASignatureFormat.Rfc3279DerSequence);
    var envelope = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1,
        algorithm = ManifestManager.SignatureAlgorithm,
        payloadBase64 = Convert.ToBase64String(signedPayload),
        signatureBase64 = Convert.ToBase64String(signature),
    });
    var verifiedManifest = ManifestManager.Verify(envelope, signingKey.ExportSubjectPublicKeyInfoPem(), now, testSourceHosts);
    Check(verifiedManifest.Artifacts.Single().Id == "sample-runtime", "firma P-256 verifica y valida el catálogo");

    var executableArtifact = new
    {
        id = "sample-installer", kind = "dependency", version = "1.0.0", architecture = "win-x64",
        displayName = "Ejemplo de dependencia", description = "Componente de prueba del instalador.",
        sourceUri = "https://downloads.example.test/sample.exe", relativePath = "packages/sample.exe",
        sizeBytes = bytes.Length, sha256 = digest, licenseId = "MIT", licenseUri = "https://opensource.org/license/mit",
        installAction = "runInstaller", installTargetPath = (string?)null, estimatedInstalledBytes = 4096L,
        publisher = "Dependency Validation", allowedExitCodes = new[] { 0, 3010 }, dependsOn = Array.Empty<string>(),
    };
    var executablePayload = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1, issuedAtUtc = now.AddMinutes(-1), expiresAtUtc = now.AddHours(2),
        artifacts = new[] { executableArtifact }, models = Array.Empty<object>(),
    });
    var executableEnvelope = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1, algorithm = ManifestManager.SignatureAlgorithm,
        payloadBase64 = Convert.ToBase64String(executablePayload),
        signatureBase64 = Convert.ToBase64String(signingKey.SignData(executablePayload,
            HashAlgorithmName.SHA256, DSASignatureFormat.Rfc3279DerSequence)),
    });
    var verifiedExecutable = ManifestManager.Verify(executableEnvelope, signingKey.ExportSubjectPublicKeyInfoPem(), now, testSourceHosts);
    Check(verifiedExecutable.Artifacts.Single().InstallAction == "runInstaller"
        && verifiedExecutable.Artifacts.Single().EstimatedInstalledBytes == 4096,
        "el manifiesto firmado puede declarar un instalador y su espacio instalado estimado");

    var traversalArtifact = executableArtifact with
    {
        relativePath = "packages/sample.zip",
        installAction = "extractZip",
        installTargetPath = "../outside",
    };
    var traversalPayload = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1, issuedAtUtc = now.AddMinutes(-1), expiresAtUtc = now.AddHours(2),
        artifacts = new[] { traversalArtifact }, models = Array.Empty<object>(),
    });
    var traversalEnvelope = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1, algorithm = ManifestManager.SignatureAlgorithm,
        payloadBase64 = Convert.ToBase64String(traversalPayload),
        signatureBase64 = Convert.ToBase64String(signingKey.SignData(traversalPayload,
            HashAlgorithmName.SHA256, DSASignatureFormat.Rfc3279DerSequence)),
    });
    await ThrowsAsync<InvalidDataException>(() => Task.Run(() => ManifestManager.Verify(
        traversalEnvelope, signingKey.ExportSubjectPublicKeyInfoPem(), now, testSourceHosts)));
    Check(true, "el manifiesto rechaza rutas de extracción que salen del destino");

    var disallowedHostPayload = Encoding.UTF8.GetBytes(Encoding.UTF8.GetString(signedPayload)
        .Replace("downloads.example.test", "unapproved.example.test", StringComparison.Ordinal));
    var disallowedHostEnvelope = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1, algorithm = ManifestManager.SignatureAlgorithm,
        payloadBase64 = Convert.ToBase64String(disallowedHostPayload),
        signatureBase64 = Convert.ToBase64String(signingKey.SignData(disallowedHostPayload, HashAlgorithmName.SHA256,
            DSASignatureFormat.Rfc3279DerSequence)),
    });
    await ThrowsAsync<InvalidDataException>(() => Task.Run(() => ManifestManager.Verify(
        disallowedHostEnvelope, signingKey.ExportSubjectPublicKeyInfoPem(), now, testSourceHosts)));
    Check(true, "el manifiesto rechaza hosts de origen HTTPS que no están en la lista aprobada");

    var zipPath = Path.Combine(temporaryRoot, "sample.zip");
    using (var zip = ZipFile.Open(zipPath, ZipArchiveMode.Create))
    {
        var entry = zip.CreateEntry("payload.bin");
        using var entryStream = entry.Open();
        await entryStream.WriteAsync(bytes);
    }
    var extractionTarget = Path.Combine(temporaryRoot, "extracted");
    long copiedFromLyingStream = 0;
    var lyingLengthAborted = false;
    using (var lyingInput = new LyingLengthStream(bytes))
    using (var discardedOutput = new MemoryStream())
    {
        try { ZipExtractor.CopyBounded(lyingInput, discardedOutput, bytes.Length - 1, ref copiedFromLyingStream); }
        catch (InvalidDataException) { lyingLengthAborted = true; }
    }
    Check(lyingLengthAborted && copiedFromLyingStream > bytes.Length - 1,
        "el límite de extracción se basa en bytes leídos, aunque Length reporte menos");
    await ThrowsAsync<InvalidDataException>(() => Task.Run(() => ZipExtractor.ExtractSafely(zipPath, extractionTarget, bytes.Length - 1)));
    Check(!Directory.Exists(extractionTarget)
        && !Directory.EnumerateDirectories(temporaryRoot).Any(path => Path.GetFileName(path).StartsWith("extracted.extracting-", StringComparison.Ordinal)),
        "la extracción cuenta bytes copiados y borra staging al superar el límite");
    ZipExtractor.ExtractSafely(zipPath, extractionTarget, bytes.Length);
    Check(File.ReadAllBytes(Path.Combine(extractionTarget, "payload.bin")).SequenceEqual(bytes),
        "el ZIP validado se publica al renombrar el staging completo");

    var modelPayloadBytes = await File.ReadAllBytesAsync(Path.Combine(repositoryRoot.FullName,
        "config", "model-manifest.payload.json"));
    var modelPayloadSignature = signingKey.SignData(modelPayloadBytes, HashAlgorithmName.SHA256,
        DSASignatureFormat.Rfc3279DerSequence);
    var modelPayloadEnvelope = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1,
        algorithm = ManifestManager.SignatureAlgorithm,
        payloadBase64 = Convert.ToBase64String(modelPayloadBytes),
        signatureBase64 = Convert.ToBase64String(modelPayloadSignature),
    });
    var verifiedModelPayload = ManifestManager.Verify(modelPayloadEnvelope,
        signingKey.ExportSubjectPublicKeyInfoPem(), now, testSourceHosts);
    Check(verifiedModelPayload.Payload.Models.Count == 12
        && verifiedModelPayload.Payload.Models.Select(model => model.Id).Distinct(StringComparer.Ordinal).Count() == 12,
        "el payload de modelos contiene 12 entradas válidas para el manifiesto firmado");
    var developmentManifestBytes = await File.ReadAllBytesAsync(Path.Combine(repositoryRoot.FullName,
        "config", "model-manifest.signed.dev.json"));
    var developmentPublicKey = await File.ReadAllTextAsync(Path.Combine(repositoryRoot.FullName,
        "config", "manifest-signing-public.dev.pem"));
    var verifiedDevelopmentManifest = ManifestManager.Verify(developmentManifestBytes, developmentPublicKey, now, testSourceHosts);
    Check(verifiedDevelopmentManifest.Payload.Models.Count == 12
        && verifiedDevelopmentManifest.PayloadSha256 == verifiedModelPayload.PayloadSha256,
        "el manifiesto firmado de desarrollo verifica con su clave pública fijada");
    var standardChoices = ChoicesFrom(standardModels);
    var standardProvisioningPlan = ModelProvisioningPlanner.Create(standardChoices, verifiedDevelopmentManifest,
        standardModels.AvailableStorageBytes);
    Check(standardProvisioningPlan.Models.Select(model => model.Id).SequenceEqual([
            "standard-chat", "standard-nucleus", "standard-coder"])
        && standardProvisioningPlan.RequiredDownloadBytes == 13_646_593_174L
        && standardProvisioningPlan.FitsExactStorage,
        "el plan estándar enlaza los tres modelos firmados y calcula el almacenamiento exacto");
    var lowDiskPlan = ModelProvisioningPlanner.Create(standardChoices, verifiedDevelopmentManifest,
        standardLowDisk.AvailableStorageBytes);
    Check(!lowDiskPlan.FitsExactStorage && lowDiskPlan.RequiredDownloadBytes == standardProvisioningPlan.RequiredDownloadBytes,
        "el plan firmado detecta falta de espacio con los tamaños exactos");
    await ThrowsAsync<InvalidDataException>(() => Task.Run(() =>
        ModelProvisioningPlanner.Create(new Dictionary<string, string>
        {
            ["chat"] = "unknown-model", ["nucleus"] = "standard-nucleus", ["coder"] = "standard-coder",
        }, verifiedDevelopmentManifest)));
    Check(true, "el plan rechaza una identidad de modelo que no aparece en el manifiesto firmado");
    var localStandardDigests = standardProvisioningPlan.Models.ToDictionary(model => model.ModelTag,
        model => model.Digest.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase)
            ? model.Digest[7..] : model.Digest, StringComparer.OrdinalIgnoreCase);
    var fullyCachedPlan = ModelProvisioningPlanner.Create(standardChoices, verifiedDevelopmentManifest,
        standardLowDisk.AvailableStorageBytes, localStandardDigests);
    Check(fullyCachedPlan.AlreadyInstalledModelIds.Count == 3
        && fullyCachedPlan.MissingModelIds.Count == 0
        && fullyCachedPlan.RequiredDownloadBytes == 0
        && fullyCachedPlan.FitsExactStorage,
        "el plan reutiliza los modelos locales por digest aunque el disco no alcance para descargarlos de nuevo");
    var partiallyCachedDigests = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
    {
        [standardProvisioningPlan.Models[0].ModelTag] = standardProvisioningPlan.Models[0].Digest,
    };
    var partiallyCachedPlan = ModelProvisioningPlanner.Create(standardChoices, verifiedDevelopmentManifest,
        standardLowDisk.AvailableStorageBytes, partiallyCachedDigests);
    Check(partiallyCachedPlan.AlreadyInstalledModelIds.Count == 1
        && partiallyCachedPlan.MissingModelIds.Count == 2
        && partiallyCachedPlan.RequiredDownloadBytes == 9_366_174_893L
        && !partiallyCachedPlan.FitsExactStorage,
        "el plan suma solo los tamaños exactos de los modelos que faltan");
    var mismatchedLocalDigests = new Dictionary<string, string>(localStandardDigests, StringComparer.OrdinalIgnoreCase)
    {
        [standardProvisioningPlan.Models[0].ModelTag] = "sha256:" + new string('f', 64),
    };
    await ThrowsAsync<InvalidDataException>(() => Task.Run(() =>
        ModelProvisioningPlanner.Create(standardChoices, verifiedDevelopmentManifest,
            standardModels.AvailableStorageBytes, mismatchedLocalDigests)));
    Check(true, "el plan bloquea un modelo local con el mismo nombre y digest distinto");
    var installedStandardApiModels = standardProvisioningPlan.Models.Select(model => new
    {
        name = model.ModelTag,
        digest = model.Digest.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase)
            ? model.Digest[7..] : model.Digest,
        size = model.MaximumDownloadBytes,
    }).ToArray();
    var provisioningTagsCalls = 0;
    var provisioningPullRequested = false;
    using var provisioningHandler = new InlineHttpHandler((request, _) =>
    {
        if (request.RequestUri!.AbsolutePath.EndsWith("/api/tags", StringComparison.Ordinal))
        {
            provisioningTagsCalls++;
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(JsonSerializer.Serialize(new { models = installedStandardApiModels }),
                    Encoding.UTF8, "application/json"),
                RequestMessage = request,
            });
        }
        provisioningPullRequested = true;
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.InternalServerError) { RequestMessage = request });
    });
    using var provisioningHttp = new HttpClient(provisioningHandler);
    var provisioningInstaller = new OllamaModelInstaller(provisioningHttp, new Uri("http://localhost:11434"));
    var provisioningService = new OllamaModelProvisioningService(provisioningInstaller, new ProvisioningEngine());
    var serviceJournal = Path.Combine(temporaryRoot, "model-provisioning", "state.json");
    var serviceResult = await provisioningService.RunAsync(standardChoices, verifiedDevelopmentManifest,
        temporaryRoot, serviceJournal);
    Check(serviceResult.Steps.All(step => step.Status == ProvisioningStepStatus.Succeeded)
        && serviceResult.Plan.MissingModelIds.Count == 0
        && provisioningTagsCalls == 4
        && !provisioningPullRequested,
        "el aprovisionamiento reanudable verifica y reutiliza modelos locales sin iniciar descargas");
    var oneRolePlan = ModelProvisioningPlanner.Create(new Dictionary<string, string>
        { ["chat"] = "standard-chat" }, verifiedDevelopmentManifest, 0);
    Check(oneRolePlan.Models.Count == 1 && oneRolePlan.Models[0].Role == "chat",
        "la elección local es opcional por función y el catálogo no fuerza tres descargas");
    await ThrowsAsync<InvalidDataException>(() => Task.Run(() => ModelProvisioningPlanner.Create(
        new Dictionary<string, string> { ["chat"] = "standard-chat", ["coder"] = "standard-chat" },
        verifiedDevelopmentManifest)));
    Check(true, "la configuración rechaza asignar un único modelo a funciones duplicadas");

    var tamperedEnvelope = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1,
        algorithm = ManifestManager.SignatureAlgorithm,
        payloadBase64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(Encoding.UTF8.GetString(signedPayload).Replace("sample-runtime", "other-runtime"))),
        signatureBase64 = Convert.ToBase64String(signature),
    });
    await ThrowsAsync<CryptographicException>(() => Task.Run(() => ManifestManager.Verify(
        tamperedEnvelope, signingKey.ExportSubjectPublicKeyInfoPem(), now)));
    Check(true, "la alteración de la carga invalida la firma");

    var expiredPayload = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1,
        issuedAtUtc = now.AddHours(-3),
        expiresAtUtc = now.AddHours(-1),
        artifacts = new[] { artifact },
        models = Array.Empty<object>(),
    });
    var expiredEnvelope = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1, algorithm = ManifestManager.SignatureAlgorithm,
        payloadBase64 = Convert.ToBase64String(expiredPayload),
        signatureBase64 = Convert.ToBase64String(signingKey.SignData(expiredPayload,
            HashAlgorithmName.SHA256, DSASignatureFormat.Rfc3279DerSequence)),
    });
    await ThrowsAsync<InvalidDataException>(() => Task.Run(() => ManifestManager.Verify(
        expiredEnvelope, signingKey.ExportSubjectPublicKeyInfoPem(), now, testSourceHosts)));
    Check(true, "el manifiesto expirado se rechaza aunque su firma sea válida");

    var escapedPathPayload = Encoding.UTF8.GetBytes(Encoding.UTF8.GetString(signedPayload)
        .Replace("runtime/sample.bin", "../outside.bin", StringComparison.Ordinal));
    var escapedPathEnvelope = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1, algorithm = ManifestManager.SignatureAlgorithm,
        payloadBase64 = Convert.ToBase64String(escapedPathPayload),
        signatureBase64 = Convert.ToBase64String(signingKey.SignData(escapedPathPayload,
            HashAlgorithmName.SHA256, DSASignatureFormat.Rfc3279DerSequence)),
    });
    await ThrowsAsync<InvalidDataException>(() => Task.Run(() => ManifestManager.Verify(
        escapedPathEnvelope, signingKey.ExportSubjectPublicKeyInfoPem(), now, testSourceHosts)));
    Check(true, "el manifiesto firmado no puede escribir fuera del directorio destino");

    var partialDirectory = Path.Combine(temporaryRoot, "download");
    var installRoot = Path.Combine(temporaryRoot, "install");
    Directory.CreateDirectory(partialDirectory);
    var partialPath = Path.Combine(installRoot, "runtime", "sample.bin.partial");
    Directory.CreateDirectory(Path.GetDirectoryName(partialPath)!);
    await File.WriteAllBytesAsync(partialPath, bytes[..4]);
    var rangeObserved = false;
    using var handler = new InlineHttpHandler((request, _) =>
    {
        rangeObserved = request.Headers.Range?.Ranges.SingleOrDefault()?.From == 4;
        var response = new HttpResponseMessage(HttpStatusCode.PartialContent)
        {
            Content = new ByteArrayContent(bytes[4..]),
            RequestMessage = request,
        };
        response.Content.Headers.ContentRange = new ContentRangeHeaderValue(4, bytes.Length - 1, bytes.Length);
        return Task.FromResult(response);
    });
    using var http = new HttpClient(handler);
    using var downloader = new ArtifactDownloader(http, testSourceHosts);
    var progress = new InlineProgress<DownloadProgress>();
    var downloadedPath = await downloader.DownloadAsync(verifiedManifest, "sample-runtime", installRoot, progress);
    Check(rangeObserved, "el descargador reanuda con el rango que coincide con el parcial");
    Check(await File.ReadAllBytesAsync(downloadedPath) is var installedBytes && installedBytes.SequenceEqual(bytes),
        "el descargador verifica el hash antes de publicar el archivo final");
    Check(progress.Last?.BytesDownloaded == bytes.Length, "el progreso informa el total verificado");
    var redirectRequests = 0;
    using var redirectHandler = new InlineHttpHandler((request, _) =>
    {
        redirectRequests++;
        var response = new HttpResponseMessage(HttpStatusCode.Redirect) { RequestMessage = request };
        response.Headers.Location = new Uri("https://unapproved.example.test/file");
        return Task.FromResult(response);
    });
    using var redirectHttp = new HttpClient(redirectHandler);
    using var redirectDownloader = new ArtifactDownloader(redirectHttp, testSourceHosts);
    await ThrowsAsync<InvalidDataException>(() => redirectDownloader.DownloadAsync(
        verifiedManifest, "sample-runtime", Path.Combine(temporaryRoot, "redirect-install")));
    Check(redirectRequests == 1, "el descargador bloquea redirecciones a hosts no aprobados antes de conectarse");
    var requestCount = 0;
    using var noRequestHandler = new InlineHttpHandler((_, _) =>
    {
        requestCount++;
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.InternalServerError));
    });
    using var noRequestHttp = new HttpClient(noRequestHandler);
    using var idempotentDownloader = new ArtifactDownloader(noRequestHttp, testSourceHosts);
    await idempotentDownloader.DownloadAsync(verifiedManifest, "sample-runtime", installRoot);
    Check(requestCount == 0, "una descarga instalada y validada se reutiliza sin red");

    // Bundle local del canal Tester: la copia no debe dejar abierto el .partial mientras se verifica.
    var localHosts = new HashSet<string>(["tester-bundle.dark.invalid"], StringComparer.OrdinalIgnoreCase);
    var localPayload = Encoding.UTF8.GetBytes(Encoding.UTF8.GetString(signedPayload)
        .Replace("downloads.example.test", "tester-bundle.dark.invalid", StringComparison.Ordinal));
    var localEnvelope = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1, algorithm = ManifestManager.SignatureAlgorithm,
        payloadBase64 = Convert.ToBase64String(localPayload),
        signatureBase64 = Convert.ToBase64String(signingKey.SignData(localPayload,
            HashAlgorithmName.SHA256, DSASignatureFormat.Rfc3279DerSequence)),
    });
    var localManifest = ManifestManager.Verify(localEnvelope, signingKey.ExportSubjectPublicKeyInfoPem(), now, localHosts);
    var localBundle = Path.Combine(temporaryRoot, "local-bundle");
    Directory.CreateDirectory(Path.Combine(localBundle, "runtime"));
    await File.WriteAllBytesAsync(Path.Combine(localBundle, "runtime", "sample.bin"), bytes);
    using var localDownloader = new ArtifactDownloader(null, localHosts, localBundle);
    var localInstall = Path.Combine(temporaryRoot, "local-install");
    var localPath = await localDownloader.DownloadAsync(localManifest, "sample-runtime", localInstall);
    Check((await File.ReadAllBytesAsync(localPath)).SequenceEqual(bytes),
        "el bundle local Tester se copia, se verifica y se publica sin error de archivo en uso");
    Check(!File.Exists(localPath + ".partial"), "la copia local no deja el archivo .partial");

    var badDigestArtifact = new
    {
        id = artifact.id, kind = artifact.kind, version = artifact.version, architecture = artifact.architecture,
        displayName = artifact.displayName, description = artifact.description,
        sourceUri = artifact.sourceUri, relativePath = "runtime/bad.bin", sizeBytes = artifact.sizeBytes,
        sha256 = new string('0', 64), licenseId = artifact.licenseId, licenseUri = artifact.licenseUri,
        publisher = artifact.publisher, allowedExitCodes = artifact.allowedExitCodes, dependsOn = artifact.dependsOn,
    };
    var badDigestPayload = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1, issuedAtUtc = now.AddMinutes(-1), expiresAtUtc = now.AddHours(2),
        artifacts = new[] { badDigestArtifact }, models = Array.Empty<object>(),
    });
    var badDigestEnvelope = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1, algorithm = ManifestManager.SignatureAlgorithm,
        payloadBase64 = Convert.ToBase64String(badDigestPayload),
        signatureBase64 = Convert.ToBase64String(signingKey.SignData(badDigestPayload,
            HashAlgorithmName.SHA256, DSASignatureFormat.Rfc3279DerSequence)),
    });
    var badDigestManifest = ManifestManager.Verify(badDigestEnvelope, signingKey.ExportSubjectPublicKeyInfoPem(), now, testSourceHosts);
    var unprefixedModelPayload = Encoding.UTF8.GetBytes(Encoding.UTF8.GetString(modelPayloadBytes)
        .Replace("sha256:", "", StringComparison.Ordinal));
    var unprefixedEnvelope = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1, algorithm = ManifestManager.SignatureAlgorithm,
        payloadBase64 = Convert.ToBase64String(unprefixedModelPayload),
        signatureBase64 = Convert.ToBase64String(signingKey.SignData(unprefixedModelPayload,
            HashAlgorithmName.SHA256, DSASignatureFormat.Rfc3279DerSequence)),
    });
    await ThrowsAsync<InvalidDataException>(() => Task.Run(() => ManifestManager.Verify(
        unprefixedEnvelope, signingKey.ExportSubjectPublicKeyInfoPem(), now, testSourceHosts)));
    Check(true, "el manifiesto de modelos exige el prefijo sha256 uniforme");
    using var corruptHandler = new InlineHttpHandler((request, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
    {
        Content = new ByteArrayContent(bytes), RequestMessage = request,
    }));
    using var corruptHttp = new HttpClient(corruptHandler);
    using var corruptDownloader = new ArtifactDownloader(corruptHttp, testSourceHosts);
    await ThrowsAsync<CryptographicException>(() => corruptDownloader.DownloadAsync(
        badDigestManifest, "sample-runtime", installRoot));
    Check(!File.Exists(Path.Combine(installRoot, "runtime", "bad.bin"))
        && !File.Exists(Path.Combine(installRoot, "runtime", "bad.bin.partial")),
        "un SHA-256 incorrect no se publica ni conserva como parcial válido");

    var modelDigest = "sha256:" + new string('a', 64);
    var modelPayload = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1,
        issuedAtUtc = now.AddMinutes(-1),
        expiresAtUtc = now.AddHours(2),
        artifacts = new[] { artifact },
        models = new[]
        {
            new
            {
                id = "chat-qwen-test", backend = "ollama", modelTag = "qwen3:4b-instruct-test",
                digest = modelDigest, maximumDownloadBytes = 1_000_000L, estimatedRamBytes = 4_000_000_000UL,
                role = "chat", sourceUri = "https://ollama.com/library/qwen3",
                licenseId = "Apache-2.0", licenseUri = "https://www.apache.org/licenses/LICENSE-2.0",
            },
        },
    });
    var modelEnvelope = JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1,
        algorithm = ManifestManager.SignatureAlgorithm,
        payloadBase64 = Convert.ToBase64String(modelPayload),
        signatureBase64 = Convert.ToBase64String(signingKey.SignData(modelPayload,
            HashAlgorithmName.SHA256, DSASignatureFormat.Rfc3279DerSequence)),
    });
    var modelManifest = ManifestManager.Verify(modelEnvelope, signingKey.ExportSubjectPublicKeyInfoPem(), now, testSourceHosts);
    var ollamaTags = 0;
    var pullRequested = false;
    using var ollamaHandler = new InlineHttpHandler(async (request, _) =>
    {
        if (request.RequestUri!.AbsolutePath.EndsWith("/api/tags", StringComparison.Ordinal))
        {
            ollamaTags++;
            var responseBody = ollamaTags == 1
                ? "{\"models\":[]}"
                : JsonSerializer.Serialize(new { models = new[] { new { name = "qwen3:4b-instruct-test", digest = modelDigest, size = 500L } } });
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(responseBody, Encoding.UTF8, "application/json"),
                RequestMessage = request,
            };
        }

        pullRequested = true;
        var pullBody = await request.Content!.ReadAsStringAsync();
        if (!pullBody.Contains("qwen3:4b-instruct-test", StringComparison.Ordinal))
            throw new InvalidOperationException("Model id was not constrained to the signed catalog.");
        var stream = new MemoryStream(Encoding.UTF8.GetBytes(
            "{\"status\":\"pulling manifest\"}\n" +
            "{\"status\":\"downloading\",\"digest\":\"sha256:layer\",\"total\":500,\"completed\":500}\n" +
            "{\"status\":\"success\"}\n"));
        return new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StreamContent(stream),
            RequestMessage = request,
        };
    });
    using var ollamaHttp = new HttpClient(ollamaHandler);
    var modelProgress = new List<ModelPullProgress>();
    var modelInstaller = new OllamaModelInstaller(ollamaHttp, new Uri("http://127.0.0.1:11434"));
    var modelResult = await modelInstaller.InstallAsync(modelManifest, "chat-qwen-test", 1_000_000L,
        new InlineProgress<ModelPullProgress>(modelProgress.Add));
    Check(pullRequested && !modelResult.AlreadyInstalled && modelResult.Digest == modelDigest,
        "la instalación Ollama usa solo un modelo firmado y confirma su digest final");
    Check(modelProgress.Any(item => item.Status == "downloading" && item.Completed == 500),
        "la instalación Ollama informa progreso por bytes");

    var pullOnMismatch = false;
    using var mismatchHandler = new InlineHttpHandler((request, _) =>
    {
        if (request.RequestUri!.AbsolutePath.EndsWith("/api/tags", StringComparison.Ordinal))
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(JsonSerializer.Serialize(new
                {
                    models = new[] { new { name = "qwen3:4b-instruct-test", digest = "sha256:" + new string('b', 64), size = 500L } },
                }), Encoding.UTF8, "application/json"), RequestMessage = request,
            });
        pullOnMismatch = true;
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.InternalServerError));
    });
    using var mismatchHttp = new HttpClient(mismatchHandler);
    var mismatchInstaller = new OllamaModelInstaller(mismatchHttp, new Uri("http://localhost:11434"));
    await ThrowsAsync<InvalidDataException>(() => mismatchInstaller.InstallAsync(modelManifest, "chat-qwen-test", 1_000_000L));
    Check(!pullOnMismatch, "un modelo local con digest distinto no se sobrescribe");

    var customPullRequested = false;
    var customInstalled = false;
    using var customHandler = new InlineHttpHandler((request, _) =>
    {
        if (request.RequestUri!.AbsolutePath.EndsWith("/api/tags", StringComparison.Ordinal))
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(JsonSerializer.Serialize(new
                {
                    models = customInstalled
                        ? new[] { new { name = "custom:latest", digest = "sha256:" + new string('c', 64), size = 123L } }
                        : Array.Empty<object>(),
                }), Encoding.UTF8, "application/json"), RequestMessage = request,
            });
        customPullRequested = true;
        customInstalled = true;
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent("{\"status\":\"success\"}\n", Encoding.UTF8, "application/x-ndjson"),
            RequestMessage = request,
        });
    });
    using var customHttp = new HttpClient(customHandler);
    var customInstaller = new OllamaModelInstaller(customHttp, new Uri("http://localhost:11434"));
    await ThrowsAsync<InvalidOperationException>(() => customInstaller.InstallCustomAsync("custom:latest", false));
    Check(!customPullRequested, "una etiqueta Ollama personalizada no se descarga sin consentimiento explícito");
    var customResult = await customInstaller.InstallCustomAsync("custom:latest", true);
    Check(customPullRequested && customResult.ModelId == "custom:latest" && customResult.SizeBytes == 123,
        "la etiqueta personalizada se descarga solo con consentimiento y se comprueba que quedó instalada");
    await ThrowsAsync<ArgumentException>(() => customInstaller.InstallCustomAsync("../../outside", true));
    Check(true, "una etiqueta Ollama personalizada con ruta inválida se rechaza antes de contactar Ollama");
}
finally
{
    Directory.Delete(temporaryRoot, recursive: true);
}

Console.WriteLine($"Validación: {failures.Count} fallo(s).");
return failures.Count == 0 ? 0 : 1;

sealed class InlineHttpHandler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> send)
    : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        => send(request, cancellationToken);
}

sealed class InlineProgress<T> : IProgress<T>
{
    private readonly Action<T>? _onReport;
    public InlineProgress(Action<T>? onReport = null) => _onReport = onReport;
    public T? Last { get; private set; }
    public void Report(T value) { Last = value; _onReport?.Invoke(value); }
}

sealed class LyingLengthStream(byte[] bytes) : Stream
{
    private readonly MemoryStream inner = new(bytes);
    public override bool CanRead => true;
    public override bool CanSeek => false;
    public override bool CanWrite => false;
    public override long Length => 1;
    public override long Position { get => inner.Position; set => throw new NotSupportedException(); }
    public override int Read(byte[] buffer, int offset, int count) => inner.Read(buffer, offset, count);
    public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        => inner.ReadAsync(buffer, cancellationToken);
    public override void Flush() => throw new NotSupportedException();
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    protected override void Dispose(bool disposing) { if (disposing) inner.Dispose(); base.Dispose(disposing); }
}

