using System.Text.Json;
using DarkSetup.Downloads;
using DarkSetup.Hardware;
using DarkSetup.Manifest;
using DarkSetup.Models;

if (args.Length == 0 || args[0] is "help" or "--help" or "-h")
{
    Console.WriteLine("DarkSetup probe [directorio-destino]");
    Console.WriteLine("DarkSetup models [directorio-destino]");
    Console.WriteLine("DarkSetup models-plan <manifiesto-firmado.json> <clave-publica.pem> <chat=id nucleus=id coder=id> [almacen-modelos]");
    Console.WriteLine("DarkSetup models-install <manifiesto-firmado.json> <clave-publica.pem> <role=id[,role=id...]> --confirm-download [almacen-modelos] [journal.json]");
    Console.WriteLine("DarkSetup models-custom-install <etiqueta-ollama> --confirm-download");
    return 0;
}

if (args[0] == "models")
{
    if (args.Length > 2)
    {
        Console.Error.WriteLine("Uso: DarkSetup models [directorio-destino]");
        return 2;
    }
    try
    {
        var root = FindProjectRoot();
        var hardware = HardwareProbe.Collect(args.ElementAtOrDefault(1));
        var selection = ModelProfileSelector.Select(hardware,
            Path.Combine(root, "config", "model-profiles.json"),
            Path.Combine(root, "DarkManager", "DarkManager", "models.json"));
        Console.WriteLine(JsonSerializer.Serialize(new { hardware, selection }, new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        }));
        return 0;
    }
    catch (Exception error)
    {
        Console.Error.WriteLine($"No se pudo seleccionar el perfil de modelos: {error.Message}");
        return 1;
    }
}

if (args[0] == "models-plan")
{
    if (args.Length is < 4 or > 5)
    {
        Console.Error.WriteLine("Uso: DarkSetup models-plan <manifiesto-firmado.json> <clave-publica.pem> <chat=id nucleus=id coder=id> [almacen-modelos]");
        return 2;
    }
    try
    {
        var root = FindProjectRoot();
        var manifest = ManifestManager.Verify(File.ReadAllBytes(args[1]), File.ReadAllText(args[2]));
        var selections = ParseRoleSelections(args[3]);
        var modelStorePath = args.ElementAtOrDefault(4) ?? GetOllamaModelStorePath();
        var hardware = HardwareProbe.Collect(modelStorePath);
        using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
        var ollama = new OllamaModelInstaller(http, GetOllamaBaseUri(root));
        var installedDigests = await ollama.ReadInstalledDigestsAsync();
        var plan = ModelProvisioningPlanner.Create(selections, manifest,
            hardware.TargetStorage.AvailableBytes, installedDigests);
        Console.WriteLine(JsonSerializer.Serialize(new { hardware, recommendations = ModelProfileSelector.Select(hardware,
            Path.Combine(root, "config", "model-profiles.json"),
            Path.Combine(root, "DarkManager", "DarkManager", "models.json")), selectedModelsByRole = selections, plan }, new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        }));
        return 0;
    }
    catch (Exception error)
    {
        Console.Error.WriteLine($"No se pudo validar el plan de modelos: {error.Message}");
        return 1;
    }
}

if (args[0] == "models-install")
{
    if (args.Length is < 5 or > 7 || args[4] != "--confirm-download")
    {
        Console.Error.WriteLine("Uso: DarkSetup models-install <manifiesto-firmado.json> <clave-publica.pem> <chat=id nucleus=id coder=id> --confirm-download [almacen-modelos] [journal.json]");
        return 2;
    }
    try
    {
        var root = FindProjectRoot();
        var manifest = ManifestManager.Verify(File.ReadAllBytes(args[1]), File.ReadAllText(args[2]));
        var selections = ParseRoleSelections(args[3]);
        var modelStorePath = Path.GetFullPath(args.ElementAtOrDefault(5) ?? GetOllamaModelStorePath());
        var journalPath = args.ElementAtOrDefault(6)
            ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "DARK", "setup", "models-state.json");
        var hardware = HardwareProbe.Collect(modelStorePath);
        using var http = new HttpClient { Timeout = Timeout.InfiniteTimeSpan };
        var installer = new OllamaModelInstaller(http, GetOllamaBaseUri(root));
        var service = new OllamaModelProvisioningService(installer, new DarkSetup.Provisioning.ProvisioningEngine());
        var progress = new Progress<ModelPullProgress>(item =>
        {
            var fraction = item.Total is > 0 && item.Completed is { } completed
                ? $" {completed}/{item.Total} bytes" : "";
            Console.WriteLine($"[{item.ModelId}] {item.Status}{fraction}");
        });
        var result = await service.RunAsync(selections, manifest, modelStorePath, journalPath, progress);
        Console.WriteLine(JsonSerializer.Serialize(result, new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        }));
        return result.Steps.All(step => step.Status == DarkSetup.Provisioning.ProvisioningStepStatus.Succeeded) ? 0 : 1;
    }
    catch (Exception error)
    {
        Console.Error.WriteLine($"No se pudo aprovisionar el perfil de modelos: {error.Message}");
        return 1;
    }
}

if (args[0] == "models-custom-install")
{
    if (args.Length != 3 || args[2] != "--confirm-download")
    {
        Console.Error.WriteLine("Uso: DarkSetup models-custom-install <etiqueta-ollama> --confirm-download");
        return 2;
    }
    try
    {
        var root = FindProjectRoot();
        using var http = new HttpClient { Timeout = Timeout.InfiniteTimeSpan };
        var installer = new OllamaModelInstaller(http, GetOllamaBaseUri(root));
        var progress = new Progress<ModelPullProgress>(item =>
        {
            var fraction = item.Total is > 0 && item.Completed is { } completed
                ? $" {completed}/{item.Total} bytes" : "";
            Console.WriteLine($"[{item.ModelId}] {item.Status}{fraction}");
        });
        var result = await installer.InstallCustomAsync(args[1], userConfirmedDownload: true, progress: progress);
        Console.WriteLine(JsonSerializer.Serialize(result, new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        }));
        return 0;
    }
    catch (Exception error)
    {
        Console.Error.WriteLine($"No se pudo instalar la etiqueta Ollama solicitada: {error.Message}");
        return 1;
    }
}

if (args[0] != "probe" || args.Length > 2)
{
    Console.Error.WriteLine("Uso: DarkSetup probe [directorio-destino]");
    return 2;
}

try
{
    var result = HardwareProbe.Collect(args.ElementAtOrDefault(1));
    Console.WriteLine(JsonSerializer.Serialize(result, new JsonSerializerOptions
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    }));
    return 0;
}
catch (Exception error)
{
    Console.Error.WriteLine($"No se pudo detectar el hardware: {error.Message}");
    return 1;
}

static string FindProjectRoot()
{
    for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
        if (File.Exists(Path.Combine(directory.FullName, "config", "model-profiles.json")))
            return directory.FullName;
    throw new DirectoryNotFoundException("No se encontró config/model-profiles.json.");
}

static Uri GetOllamaBaseUri(string projectRoot)
{
    var overrideUrl = Environment.GetEnvironmentVariable("DARK_OLLAMA_URL");
    if (!string.IsNullOrWhiteSpace(overrideUrl)) return new Uri(overrideUrl, UriKind.Absolute);
    using var runtime = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(projectRoot, "config", "runtime.json")));
    var configuredUrl = runtime.RootElement.GetProperty("services").GetProperty("ollama").GetProperty("url").GetString();
    return new Uri(configuredUrl ?? throw new InvalidDataException("Falta services.ollama.url en runtime.json."), UriKind.Absolute);
}

static string GetOllamaModelStorePath()
{
    var configuredPath = Environment.GetEnvironmentVariable("OLLAMA_MODELS");
    return Path.GetFullPath(string.IsNullOrWhiteSpace(configuredPath)
        ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".ollama", "models")
        : configuredPath);
}

static IReadOnlyDictionary<string, string> ParseRoleSelections(string value)
{
    var result = new Dictionary<string, string>(StringComparer.Ordinal);
    foreach (var selection in value.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
    {
        var separator = selection.IndexOf('=');
        if (separator <= 0 || separator == selection.Length - 1
            || !result.TryAdd(selection[..separator].Trim(), selection[(separator + 1)..].Trim()))
            throw new ArgumentException("Usa asignaciones explícitas separadas por coma, por ejemplo chat=standard-chat,coder=standard-coder; puedes omitir funciones.");
    }
    return result;
}
