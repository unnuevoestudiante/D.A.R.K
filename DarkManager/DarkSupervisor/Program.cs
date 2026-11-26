using System.Diagnostics;
using System.Net;
using System.Net.Http;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Runtime.InteropServices;

// Una sola sesión por usuario: abrir D.A.R.K. de nuevo (acceso directo, inicio con Windows y el botón del instalador a la
// vez) no debe lanzar otra copia que choque con los puertos de la primera.
using var unaSola = new Mutex(initiallyOwned: true, @"Local\DARK.Supervisor", out var esLaPrimera);
if (!esLaPrimera)
{
    Console.WriteLine("[Supervisor] D.A.R.K. ya está abierto; no se inicia otra copia.");
    return;
}

var root = FindProjectRoot(args.FirstOrDefault());
var installedLayout = InstalledRuntimeLayout.Resolve(root);
var userDataRoot = installedLayout is null
    ? null
    : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "DARK");
// Sin consola (WinExe): instalado, lo que el Supervisor cuenta va a un registro; en desarrollo, a la terminal que lo lanzó.
string? supervisorLog = null;
if (userDataRoot is not null)
{
    try
    {
        var logDirectory = Path.Combine(userDataRoot, "logs");
        Directory.CreateDirectory(logDirectory);
        supervisorLog = Path.Combine(logDirectory, "supervisor.log");
        var writer = new StreamWriter(supervisorLog, append: false) { AutoFlush = true };
        Console.SetOut(writer);
        Console.SetError(writer);
    }
    catch (Exception error) when (error is IOException or UnauthorizedAccessException)
    {
        supervisorLog = null;
    }
}
else
{
    NativeMethods.AttachConsole(NativeMethods.AttachParentProcess);
}
var configPath = ResolveRuntimeConfig(root, installedLayout is not null, userDataRoot);
if (installedLayout is not null
    && string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("DARK_RUNTIME_CONFIG")))
{
    EnsureInstalledUiEndpoint(configPath);
    EnsureInstalledLoopback(configPath);
}
using var runtimeDocument = JsonDocument.Parse(File.ReadAllText(configPath));
var services = runtimeDocument.RootElement.GetProperty("services");
var uiUrl = RequiredUrl(services, "ui");
var managerUrl = RequiredUrl(services, "manager");
var taskManagerUrl = RequiredUrl(services, "taskManager");
var overlayHttpPort = RequiredPort(services, "overlay", "httpPort");
var overlayHealthUrl = $"http://localhost:{overlayHttpPort}/health";

string python;
var pythonDir = Path.Combine(root, "dark_python");
var frontendDir = Path.Combine(root, "dark_frontend");
var electronDir = Path.Combine(root, "dark_electron");
var processes = new List<ManagedProcess>();
var shutdown = new CancellationTokenSource();
ConsoleCancelEventHandler cancelHandler = (_, eventArgs) =>
{
    eventArgs.Cancel = true;
    shutdown.Cancel();
};
Console.CancelKeyPress += cancelHandler;

try
{
    python = ResolvePython(root);
    EnsureEndpointFree(managerUrl, "DarkManager");
    EnsureEndpointFree(taskManagerUrl, "DarkTaskManager");

    var managerExecutable = installedLayout?.ManagerExecutable
        ?? Path.Combine(root, "DarkManager", "DarkManager", "bin", "Debug", "net10.0", "DarkManager.exe");
    var taskManagerExecutable = installedLayout?.TaskManagerExecutable
        ?? Path.Combine(root, "DarkManager", "DarkTaskManager", "bin", "Debug", "net10.0", "DarkTaskManager.exe");
    var manager = StartManager("DarkManager", managerExecutable);
    var taskManager = StartManager("DarkTaskManager", taskManagerExecutable);
    if (!await WaitForHttp(managerUrl.TrimEnd('/') + "/status", manager,
            TimeSpan.FromSeconds(30), shutdown.Token))
        throw new InvalidOperationException($"DarkManager no respondió en {managerUrl}.");
    if (!await WaitForHttp(taskManagerUrl.TrimEnd('/') + "/tasks", taskManager,
            TimeSpan.FromSeconds(30), shutdown.Token))
        throw new InvalidOperationException($"DarkTaskManager no respondió en {taskManagerUrl}.");

    // Keep the existing Python voice watchdog, but make it an owned child of
    // this host instead of starting its children from the Núcleo.
    var voiceEnvironment = new Dictionary<string, string> { ["DARK_RUNTIME_CONFIG"] = configPath };
    if (userDataRoot is not null)
    {
        voiceEnvironment["DARK_USER_DATA_DIR"] = Path.Combine(userDataRoot, "data");
        voiceEnvironment["DARK_USER_LOG_DIR"] = Path.Combine(userDataRoot, "logs");
    }
    processes.Add(Start("Voice supervisor", python, pythonDir,
        ["-m", "voz.supervisor", "--host"],
        voiceEnvironment));

    var commonEnvironment = new Dictionary<string, string>
    {
        ["DARK_RUNTIME_CONFIG"] = configPath,
        ["DARK_LLM_PROVIDER"] = "conmutado",
    };
    if (userDataRoot is not null)
    {
        commonEnvironment["DARK_USER_DATA_DIR"] = Path.Combine(userDataRoot, "data");
        commonEnvironment["DARK_USER_LOG_DIR"] = Path.Combine(userDataRoot, "logs");
    }
    ManagedProcess frontend;
    if (installedLayout is null)
    {
        frontend = StartShellCommand("DARK UI", "npm run dev", frontendDir, commonEnvironment);
    }
    else
    {
        var uiEndpoint = new Uri(uiUrl);
        var uiEnvironment = new Dictionary<string, string>(commonEnvironment)
        {
            ["HOST"] = "127.0.0.1",
            ["PORT"] = uiEndpoint.Port.ToString(System.Globalization.CultureInfo.InvariantCulture),
        };
        frontend = Start("DARK UI", installedLayout.NodeExecutable, installedLayout.UiOutputDirectory,
            [Path.Combine("server", "index.mjs")], uiEnvironment);
    }
    processes.Add(frontend);

    var readyToken = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
    var unlockToken = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
    commonEnvironment["DARK_PROCESS_OWNER"] = "external";
    commonEnvironment["DARK_LOCK_READY_TOKEN"] = readyToken;
    commonEnvironment["DARK_LOCK_UNLOCK_TOKEN"] = unlockToken;
    processes.Add(Start("DARK Núcleo", python, pythonDir,
        ["-m", "nucleo.dark_nucleo"], commonEnvironment));
    var nucleus = processes[^1];
    if (!await WaitForHttp(overlayHealthUrl, nucleus, TimeSpan.FromSeconds(45), shutdown.Token))
        throw new InvalidOperationException($"El puente Overlay no respondió en {overlayHealthUrl}.");

    if (await WaitForHttp(uiUrl, frontend, TimeSpan.FromSeconds(60), shutdown.Token))
    {
        var electron = installedLayout?.ElectronExecutable
            ?? Path.Combine(electronDir, "node_modules", "electron", "dist", "electron.exe");
        if (File.Exists(electron))
        {
            var electronEnvironment = new Dictionary<string, string>(commonEnvironment)
            {
                ["DARK_UI_URL"] = uiUrl.TrimEnd('/') + "/?transparent=1&lock=1",
            };
            var electronWorkingDirectory = installedLayout?.ElectronAppDirectory ?? electronDir;
            IReadOnlyList<string> electronArguments = installedLayout is null ? ["main.cjs"] : ["."];
            processes.Add(Start("DARK Electron", electron, electronWorkingDirectory,
                electronArguments, electronEnvironment));
        }
        else
        {
            throw new FileNotFoundException(
                "Electron no está instalado. Ejecuta 'npm ci' desde dark_electron antes de iniciar DARK.",
                electron);
        }
    }
    else if (!shutdown.IsCancellationRequested)
    {
        throw new InvalidOperationException($"La UI no respondió en {uiUrl} en 60 segundos.");
    }

    Console.WriteLine("[Supervisor] Sesión iniciada. Ctrl+C para cerrar los procesos que inició.");
    while (!shutdown.IsCancellationRequested)
    {
        var exited = processes.FirstOrDefault(process => process.HasExited);
        if (exited is not null)
            throw new InvalidOperationException($"El proceso {exited.Name} terminó durante la sesión.");
        await Task.Delay(1000, shutdown.Token);
    }
}
catch (OperationCanceledException) when (shutdown.IsCancellationRequested)
{
    // Normal shutdown.
}
catch (Exception error)
{
    Console.Error.WriteLine($"[Supervisor] {error.Message}");
    Environment.ExitCode = 1;
    if (installedLayout is not null)
    {
        // Sin consola, un fallo al abrir sería invisible: se avisa con una ventana normal de Windows.
        NativeMethods.MessageBoxW(IntPtr.Zero,
            "D.A.R.K. no pudo abrirse.\n\n" + error.Message
                + (supervisorLog is null ? "" : "\n\nDetalles en:\n" + supervisorLog),
            "D.A.R.K.", 0x10 /* MB_ICONERROR */);
    }
}
finally
{
    foreach (var process in processes.AsEnumerable().Reverse())
        await process.StopAsync();
    Console.CancelKeyPress -= cancelHandler;
    shutdown.Dispose();
}

ManagedProcess StartManager(string name, string executable)
{
    if (!File.Exists(executable))
        throw new FileNotFoundException($"No se encontró {name}. Compile primero el proyecto .NET.", executable);
    var environment = new Dictionary<string, string> { ["DARK_RUNTIME_CONFIG"] = configPath };
    if (userDataRoot is not null)
    {
        environment["DARK_USER_DATA_DIR"] = Path.Combine(userDataRoot, "data");
        environment["DARK_USER_LOG_DIR"] = Path.Combine(userDataRoot, "logs");
    }
    var process = Start(name, executable, Path.GetDirectoryName(executable)!, [], environment);
    processes.Add(process);
    return process;
}

static string ResolveRuntimeConfig(string root, bool installed, string? userDataRoot)
{
    var configured = Environment.GetEnvironmentVariable("DARK_RUNTIME_CONFIG");
    if (!string.IsNullOrWhiteSpace(configured)) return Path.GetFullPath(configured);
    var bundledConfig = Path.Combine(root, "config", "runtime.json");
    if (!installed || userDataRoot is null) return bundledConfig;

    var configDirectory = Path.Combine(userDataRoot, "config");
    var configPath = Path.Combine(configDirectory, "runtime.json");
    if (File.Exists(configPath)) return configPath;

    Directory.CreateDirectory(configDirectory);
    Directory.CreateDirectory(Path.Combine(userDataRoot, "data"));
    Directory.CreateDirectory(Path.Combine(userDataRoot, "models"));
    Directory.CreateDirectory(Path.Combine(userDataRoot, "logs"));
    Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), "DARK"));
    Directory.CreateDirectory(Path.Combine(userDataRoot, "cache"));
    using var source = JsonDocument.Parse(File.ReadAllText(bundledConfig));
    var settings = JsonNode.Parse(source.RootElement.GetRawText())
        ?? throw new InvalidDataException("config/runtime.json está vacío.");
    settings["profile"] = "installed";
    settings["paths"]!["models"] = Path.Combine(userDataRoot, "models");
    settings["paths"]!["logs"] = Path.Combine(userDataRoot, "logs");
    settings["paths"]!["temporary"] = Path.Combine(Path.GetTempPath(), "DARK");
    settings["paths"]!["cache"] = Path.Combine(userDataRoot, "cache");
    File.WriteAllText(configPath, settings.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    return configPath;
}

// La distribucion base solo escucha en este equipo: ningun servicio debe quedar expuesto en
// 0.0.0.0 (toda la red). El acceso desde LAN (p. ej. la TV) sera una funcion explicita futura.
static void EnsureInstalledLoopback(string configPath)
{
    var settings = JsonNode.Parse(File.ReadAllText(configPath))
        ?? throw new InvalidDataException("config/runtime.json está vacío.");
    var changed = false;
    if (settings["services"] is JsonObject services)
    {
        foreach (var (_, service) in services)
        {
            if (service is JsonObject entry
                && entry["host"]?.GetValue<string>() is "0.0.0.0" or "::" or "*")
            {
                entry["host"] = "127.0.0.1";
                changed = true;
            }
        }
    }
    if (!changed) return;
    var temporaryPath = configPath + ".tmp";
    File.WriteAllText(temporaryPath, settings.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    File.Move(temporaryPath, configPath, overwrite: true);
}

static void EnsureInstalledUiEndpoint(string configPath)
{
    using var document = JsonDocument.Parse(File.ReadAllText(configPath));
    var services = document.RootElement.GetProperty("services");
    var ui = services.GetProperty("ui");
    var uiAddress = ui.GetProperty("url").GetString();
    if (!Uri.TryCreate(uiAddress, UriKind.Absolute, out var currentUi)
        || currentUi.Scheme is not ("http" or "https"))
        throw new InvalidDataException("services.ui.url no es una URL HTTP válida.");

    var reservedPorts = new HashSet<int>();
    foreach (var service in services.EnumerateObject())
    {
        if (service.NameEquals("ui")) continue;
        foreach (var property in service.Value.EnumerateObject())
        {
            if (property.NameEquals("url") && property.Value.ValueKind == JsonValueKind.String
                && Uri.TryCreate(property.Value.GetString(), UriKind.Absolute, out var endpoint)
                && endpoint.Port is >= 1 and <= 65535)
                reservedPorts.Add(endpoint.Port);
            else if (property.NameEquals("port") || property.NameEquals("httpPort")
                || property.NameEquals("websocketPort"))
            {
                if (property.Value.TryGetInt32(out var port) && port is >= 1 and <= 65535)
                    reservedPorts.Add(port);
            }
        }
    }

    if (!reservedPorts.Contains(currentUi.Port) && CanBindLoopback(currentUi.Port)) return;

    var settings = JsonNode.Parse(File.ReadAllText(configPath))
        ?? throw new InvalidDataException("config/runtime.json está vacío.");
    var uiSettings = settings["services"]?["ui"] as JsonObject
        ?? throw new InvalidDataException("Falta services.ui en config/runtime.json.");
    var replacementPort = FindAvailableUiPort(reservedPorts);
    var replacement = new UriBuilder(currentUi) { Port = replacementPort };
    uiSettings["url"] = replacement.Uri.ToString().TrimEnd('/');

    var temporaryPath = configPath + ".tmp";
    File.WriteAllText(temporaryPath, settings.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    File.Move(temporaryPath, configPath, overwrite: true);
}

static int FindAvailableUiPort(IReadOnlySet<int> reservedPorts)
{
    for (var attempt = 0; attempt < 32; attempt++)
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        if (!reservedPorts.Contains(port)) return port;
    }
    throw new InvalidOperationException("No se pudo asignar un puerto local libre para la UI de DARK.");
}

static bool CanBindLoopback(int port)
{
    try
    {
        var listener = new TcpListener(IPAddress.Loopback, port);
        listener.Start();
        listener.Stop();
        return true;
    }
    catch (SocketException)
    {
        return false;
    }
}

static ManagedProcess Start(string name, string fileName, string workingDirectory,
    IReadOnlyList<string> arguments, IReadOnlyDictionary<string, string>? environment = null)
{
    var info = new ProcessStartInfo(fileName)
    {
        WorkingDirectory = workingDirectory,
        UseShellExecute = false,
        CreateNoWindow = true,
    };
    foreach (var argument in arguments) info.ArgumentList.Add(argument);
    if (environment is not null)
        foreach (var (key, value) in environment) info.Environment[key] = value;

    var process = Process.Start(info) ?? throw new InvalidOperationException($"No se pudo iniciar {name}.");
    ProcessJob.Assign(process);
    Console.WriteLine($"[Supervisor] {name} iniciado (PID {process.Id}).");
    return new ManagedProcess(name, process);
}

static ManagedProcess StartShellCommand(string name, string command, string workingDirectory,
    IReadOnlyDictionary<string, string>? environment = null)
{
    var commandInterpreter = Environment.GetEnvironmentVariable("ComSpec") ?? "cmd.exe";
    return Start(name, commandInterpreter, workingDirectory, ["/d", "/s", "/c", command], environment);
}

static string RequiredUrl(JsonElement services, string service)
{
    var url = services.GetProperty(service).GetProperty("url").GetString();
    if (!Uri.TryCreate(url, UriKind.Absolute, out var parsed)
        || parsed.Scheme is not ("http" or "https"))
        throw new InvalidDataException($"services.{service}.url no es una URL HTTP válida.");
    return url!;
}

static string ResolvePython(string root)
{
    var privateRuntime = Path.Combine(root, "python", "python.exe");
    var virtualEnvironment = Path.Combine(root, ".venv", "Scripts", "python.exe");
    var candidates = (File.Exists(privateRuntime)
            ? new[] { privateRuntime }
            : new[] { virtualEnvironment, "python" })
        .Where(candidate => candidate == "python" || File.Exists(candidate))
        .Distinct(StringComparer.OrdinalIgnoreCase);
    var failures = new List<string>();
    foreach (var candidate in candidates)
    {
        try
        {
            using var check = new Process
            {
                StartInfo = new ProcessStartInfo(candidate)
                {
                    WorkingDirectory = Path.Combine(root, "dark_python"),
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                },
            };
            check.StartInfo.ArgumentList.Add("-c");
            check.StartInfo.ArgumentList.Add("import requests, websockets");
            if (!check.Start()) continue;
            if (!check.WaitForExit(10_000))
            {
                check.Kill(entireProcessTree: true);
                failures.Add($"{candidate}: comprobación agotó el tiempo límite");
                continue;
            }
            if (check.ExitCode == 0) return candidate;
            var detail = check.StandardError.ReadToEnd().Trim();
            failures.Add($"{candidate}: {(string.IsNullOrWhiteSpace(detail) ? "faltan dependencias" : detail)}");
        }
        catch (Exception error) when (error is InvalidOperationException or System.ComponentModel.Win32Exception)
        {
            failures.Add($"{candidate}: {error.Message}");
        }
    }
    throw new InvalidOperationException(
        "No hay un runtime Python utilizable. Active .venv e instale las dependencias ya declaradas " +
        "en dark_python/requirements-core.txt. " + string.Join("; ", failures));
}

static int RequiredPort(JsonElement services, string service, string property)
{
    if (!services.TryGetProperty(service, out var section)
        || !section.TryGetProperty(property, out var value)
        || !value.TryGetInt32(out var port) || port is < 1 or > 65535)
        throw new InvalidDataException($"services.{service}.{property} debe ser un puerto válido.");
    return port;
}

static string FindProjectRoot(string? explicitRoot)
{
    if (!string.IsNullOrWhiteSpace(explicitRoot))
    {
        var resolved = Path.GetFullPath(explicitRoot);
        if (File.Exists(Path.Combine(resolved, "config", "runtime.json"))) return resolved;
        throw new DirectoryNotFoundException($"No se encontró config/runtime.json en {resolved}.");
    }

    for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
        if (File.Exists(Path.Combine(directory.FullName, "config", "runtime.json"))) return directory.FullName;
    throw new DirectoryNotFoundException("No se encontró config/runtime.json. Use --project-root <ruta>.");
}

static async Task<bool> WaitForHttp(string url, ManagedProcess process, TimeSpan timeout, CancellationToken cancellationToken)
{
    using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
    var deadline = DateTime.UtcNow + timeout;
    while (DateTime.UtcNow < deadline && !cancellationToken.IsCancellationRequested)
    {
        if (process.HasExited) return false;
        try
        {
            using var response = await client.GetAsync(url, cancellationToken);
            if (response.IsSuccessStatusCode) return true;
        }
        catch (HttpRequestException) { }
        catch (TaskCanceledException) when (!cancellationToken.IsCancellationRequested) { }
        await Task.Delay(500, cancellationToken);
    }
    return false;
}

static void EnsureEndpointFree(string url, string serviceName)
{
    if (!Uri.TryCreate(url, UriKind.Absolute, out var endpoint))
        throw new InvalidDataException($"No pude comprobar el endpoint de {serviceName}: {url}.");

    var listeners = IPGlobalProperties.GetIPGlobalProperties()
        .GetActiveTcpListeners()
        .Where(address => address.Port == endpoint.Port)
        .ToArray();
    if (listeners.Length > 0)
        throw new InvalidOperationException(
            $"El puerto de {serviceName} ({endpoint.Port}) ya está en escucha en " +
            $"{string.Join(", ", listeners.Select(address => address.Address.ToString()))}. " +
            "Cierre la instancia existente antes de iniciar una sesión administrada. " +
            "El Supervisor no termina procesos que no haya iniciado.");
}

/// <summary>
/// Job Object de Windows con KILL_ON_JOB_CLOSE: si el Supervisor termina por cualquier causa
/// (cerrar su consola, cerrar sesion, fallo) Windows termina todos los procesos asignados, asi
/// no quedan DarkManager, Node o Python huerfanos ocupando puertos y bloqueando archivos.
/// </summary>
static class ProcessJob
{
    private static readonly IntPtr Handle = Create();

    private static IntPtr Create()
    {
        try
        {
            var job = CreateJobObject(IntPtr.Zero, null);
            if (job == IntPtr.Zero) return IntPtr.Zero;
            var info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
            info.BasicLimitInformation.LimitFlags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            var size = System.Runtime.InteropServices.Marshal.SizeOf<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>();
            var pointer = System.Runtime.InteropServices.Marshal.AllocHGlobal(size);
            try
            {
                System.Runtime.InteropServices.Marshal.StructureToPtr(info, pointer, false);
                if (!SetInformationJobObject(job, 9, pointer, (uint)size)) return IntPtr.Zero;
            }
            finally { System.Runtime.InteropServices.Marshal.FreeHGlobal(pointer); }
            return job;
        }
        catch (Exception error) when (error is DllNotFoundException or EntryPointNotFoundException
                                          or System.Runtime.InteropServices.COMException)
        {
            return IntPtr.Zero;
        }
    }

    public static void Assign(Process process)
    {
        if (Handle == IntPtr.Zero) return;
        try
        {
            if (!AssignProcessToJobObject(Handle, process.Handle))
                Console.Error.WriteLine($"[Supervisor] Aviso: no se pudo asociar el PID {process.Id} al job de cierre.");
        }
        catch (Exception error) when (error is InvalidOperationException or System.ComponentModel.Win32Exception)
        {
            // El proceso termino antes de asociarse.
        }
    }

    [System.Runtime.InteropServices.DllImport("kernel32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    private static extern IntPtr CreateJobObject(IntPtr attributes, string? name);

    [System.Runtime.InteropServices.DllImport("kernel32.dll")]
    [return: System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.Bool)]
    private static extern bool SetInformationJobObject(IntPtr job, int infoClass, IntPtr info, uint size);

    [System.Runtime.InteropServices.DllImport("kernel32.dll")]
    [return: System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.Bool)]
    private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    private struct JOBOBJECT_BASIC_LIMIT_INFORMATION
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    private struct IO_COUNTERS
    {
        public ulong ReadOperationCount;
        public ulong WriteOperationCount;
        public ulong OtherOperationCount;
        public ulong ReadTransferCount;
        public ulong WriteTransferCount;
        public ulong OtherTransferCount;
    }

    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    private struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    {
        public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
        public IO_COUNTERS IoInfo;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }
}

sealed class ManagedProcess(string name, Process process)
{
    public string Name => name;
    public bool HasExited
    {
        get { try { return process.HasExited; } catch (InvalidOperationException) { return true; } }
    }

    public async Task StopAsync()
    {
        try
        {
            if (process.HasExited) return;
            Console.WriteLine($"[Supervisor] Cerrando {name}...");
            process.Kill(entireProcessTree: true);
            await process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(10));
        }
        catch (InvalidOperationException) { }
        catch (System.ComponentModel.Win32Exception error)
        {
            Console.Error.WriteLine($"[Supervisor] No se pudo cerrar {name}: {error.Message}");
        }
        catch (TimeoutException)
        {
            Console.Error.WriteLine($"[Supervisor] Tiempo agotado cerrando {name}.");
        }
        finally { process.Dispose(); }
    }
}

sealed record InstalledRuntimeLayout(
    string PythonExecutable,
    string ManagerExecutable,
    string TaskManagerExecutable,
    string NodeExecutable,
    string UiOutputDirectory,
    string ElectronExecutable,
    string ElectronAppDirectory)
{
    public static InstalledRuntimeLayout? Resolve(string root)
    {
        var services = Path.Combine(root, "services");
        var ui = Path.Combine(root, "ui");
        var python = Path.Combine(root, "python", "python.exe");
        if (!Directory.Exists(services) && !Directory.Exists(ui) && !File.Exists(python))
            return null;

        var layout = new InstalledRuntimeLayout(
            python,
            Path.Combine(services, "DarkManager", "DarkManager.exe"),
            Path.Combine(services, "DarkTaskManager", "DarkTaskManager.exe"),
            Path.Combine(root, "node", "node.exe"),
            Path.Combine(ui, ".output"),
            Path.Combine(root, "electron", "runtime", "electron.exe"),
            Path.Combine(root, "electron", "app"));
        var requiredFiles = new[]
        {
            layout.PythonExecutable,
            layout.ManagerExecutable,
            layout.TaskManagerExecutable,
            layout.NodeExecutable,
            Path.Combine(layout.UiOutputDirectory, "server", "index.mjs"),
            layout.ElectronExecutable,
            Path.Combine(layout.ElectronAppDirectory, "main.cjs"),
            Path.Combine(layout.ElectronAppDirectory, "preload.js"),
        };
        var missing = requiredFiles.Where(path => !File.Exists(path)).ToArray();
        if (missing.Length > 0)
            throw new FileNotFoundException(
                "El layout de la aplicación instalada está incompleto: " + string.Join(", ", missing));
        return layout;
    }
}

static class NativeMethods
{
    public const int AttachParentProcess = -1;

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool AttachConsole(int processId);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int MessageBoxW(IntPtr owner, string text, string caption, uint type);
}
