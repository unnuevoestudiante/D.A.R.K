using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using LibreHardwareMonitor.Hardware;

var builder = WebApplication.CreateBuilder(args);

builder.Host.UseWindowsService(options =>
{
    options.ServiceName = "DARK Resource Manager";
});

var app = builder.Build();

var runtimeConfigPath = Environment.GetEnvironmentVariable("DARK_RUNTIME_CONFIG")
    ?? Path.Combine(AppContext.BaseDirectory, "runtime.json");
using var runtimeConfig = JsonDocument.Parse(File.ReadAllText(runtimeConfigPath));
var runtimeServices = runtimeConfig.RootElement.GetProperty("services");
var ollamaUrl = runtimeServices.GetProperty("ollama").GetProperty("url").GetString()
    ?? throw new InvalidDataException("services.ollama.url vacío en runtime.json");
var managerUrl = runtimeServices.GetProperty("manager").GetProperty("url").GetString()
    ?? throw new InvalidDataException("services.manager.url vacío en runtime.json");
var managerModelKeepAlive = runtimeConfig.RootElement.GetProperty("runtime")
    .GetProperty("managerModelKeepAlive").GetString()
    ?? throw new InvalidDataException("runtime.managerModelKeepAlive vacío en runtime.json");

var baseDir = AppContext.BaseDirectory;
var modelsJsonPath = Path.Combine(baseDir, "models.json");
var logsDir = Environment.GetEnvironmentVariable("DARK_USER_LOG_DIR") is { Length: > 0 } configuredLogs
    ? Path.GetFullPath(configuredLogs)
    : baseDir;
Directory.CreateDirectory(logsDir);
var logPath = Path.Combine(logsDir, "resource-manager.log");

Log($"DEBUG: Cargando models.json desde: {modelsJsonPath}");
Log($"DEBUG: models.json existe: {File.Exists(modelsJsonPath)}");

if (!File.Exists(modelsJsonPath))
{
    Log($"ERROR: models.json no encontrado en {modelsJsonPath}");
    throw new FileNotFoundException($"models.json no encontrado en {modelsJsonPath}");
}

var modelsJsonContent = File.ReadAllText(modelsJsonPath);
Log($"DEBUG: Contenido de models.json: {modelsJsonContent}");

var modelRegistry = JsonSerializer.Deserialize<Dictionary<string, ModelInfo>>(modelsJsonContent);
if (modelRegistry == null)
{
    Log($"ERROR: models.json deserializado como null");
    throw new Exception("models.json deserializado como null");
}

Log($"DEBUG: modelRegistry cargado con {modelRegistry.Count} modelo(s)");
foreach (var kvp in modelRegistry)
{
    Log($"DEBUG: Registro: '{kvp.Key}' -> {kvp.Value.RamEstimadaMB}MB (prioridad {kvp.Value.Prioridad})");
}

var OLLAMA_URL = ollamaUrl.TrimEnd('/');

// === Presupuesto dinámico ===
// 55% de la RAM total para Ollama, el resto para el SO, Python,
// Whisper, Piper, Electron, Vite, etc.
var memStatus = new MEMORYSTATUSEX();
memStatus.dwLength = (uint)Marshal.SizeOf(memStatus);
GlobalMemoryStatusEx(ref memStatus);
long totalRamMB = (long)(memStatus.ullTotalPhys / (1024 * 1024));
const double FRACCION_OLLAMA = 0.55;
long PRESUPUESTO_TOTAL_MB = (long)(totalRamMB * FRACCION_OLLAMA);
Log($"PRESUPUESTO_TOTAL_MB calculado dinámicamente: {PRESUPUESTO_TOTAL_MB}MB (RAM total {totalRamMB}MB)");

var recursoLock = new SemaphoreSlim(1, 1);

var cpuCounter = new CpuUsageCounter();
cpuCounter.NextValue();

Computer? hardwareComputer = null;
var hardwareLock = new object();
var hardwareListo = false;

void InicializarHardwareMonitor()
{
    try
    {
        var computer = new Computer { IsCpuEnabled = true, IsGpuEnabled = true };
        computer.Open();
        lock (hardwareLock)
        {
            hardwareComputer = computer;
            hardwareListo = true;
        }
        Log("Monitor de hardware inicializado correctamente (temperatura disponible)");
    }
    catch (Exception ex)
    {
        Log($"WARN: No se pudo inicializar el monitor de hardware: {ex.GetType().Name} - {ex.Message}");
    }
}

float? ObtenerTemperaturaCpuC()
{
    lock (hardwareLock)
    {
        if (!hardwareListo || hardwareComputer is null) return null;
    }

    float? maxTemp = null;
    var cpusEncontrados = 0;
    var sensoresTempEncontrados = 0;

    foreach (var hardware in hardwareComputer.Hardware)
    {
        if (hardware.HardwareType != HardwareType.Cpu) continue;
        cpusEncontrados++;
        hardware.Update();
        foreach (var sensor in hardware.Sensors)
        {
            if (sensor.SensorType == SensorType.Temperature)
            {
                sensoresTempEncontrados++;
                Log($"DEBUG sensor temp: '{sensor.Name}' valor={(sensor.Value.HasValue ? sensor.Value.Value.ToString("F1") : "null")}");
                if (sensor.Value.HasValue && (maxTemp is null || sensor.Value > maxTemp))
                    maxTemp = sensor.Value;
            }
        }
    }

    if (cpusEncontrados == 0)
        Log("DEBUG: no se encontró ningún hardware de tipo Cpu en hardwareComputer.Hardware");
    else if (sensoresTempEncontrados == 0)
        Log($"DEBUG: se encontraron {cpusEncontrados} CPU(s) pero ningún sensor de tipo Temperature");

    return maxTemp;
}

void Log(string mensaje)
{
    var linea = $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {mensaje}";
    File.AppendAllText(logPath, linea + Environment.NewLine);
    Console.WriteLine(linea);
}

var httpClient = new HttpClient();

app.MapGet("/status", async () =>
{
    var ramDisponibleMB = ObtenerRamDisponibleMB();

    List<OllamaModel> modelosActivos;
    bool ollamaDisponible;
    try
    {
        modelosActivos = await ObtenerModelosActivosDeOllama();
        ollamaDisponible = true;
        Log($"DEBUG: Ollama devolvió {modelosActivos.Count} modelo(s) activo(s)");
        foreach (var m in modelosActivos)
        {
            Log($"DEBUG: Modelo Ollama: '{m.Name}' ({m.Size / (1024*1024)}MB)");
        }
    }
    catch (Exception ex)
    {
        Log($"WARN: no se pudo consultar Ollama en /status: {ex.GetType().Name} - {ex.Message}");
        modelosActivos = new List<OllamaModel>();
        ollamaDisponible = false;
    }

    var ramUsadaPorModelos = SumarRamEstimada(modelosActivos);
    Log($"DEBUG: RAM usada por modelos calculada: {ramUsadaPorModelos}MB");

    var cpuUsoPct = cpuCounter.NextValue();
    var cpuTempC = ObtenerTemperaturaCpuC();

    return Results.Ok(new
    {
        ramDisponibleMB,
        ollamaDisponible,
        modelosActivos,
        ramUsadaPorModelosMB = ramUsadaPorModelos,
        presupuestoTotalMB = PRESUPUESTO_TOTAL_MB,
        presupuestoRestanteMB = PRESUPUESTO_TOTAL_MB - ramUsadaPorModelos,
        cpuUsoPct = Math.Round(cpuUsoPct, 1),
        cpuTempC = cpuTempC.HasValue ? Math.Round(cpuTempC.Value, 1) : (double?)null
    });
});

app.MapPost("/load/{modelo}", async (string modelo) =>
{
    if (!modelRegistry.TryGetValue(modelo, out var info))
        return Results.BadRequest(new { error = $"Modelo '{modelo}' no está registrado en models.json" });

    await recursoLock.WaitAsync();
    try
    {
        var modelosActivos = await ObtenerModelosActivosDeOllama();

        if (modelosActivos.Any(m => m.Name.Equals(modelo, StringComparison.OrdinalIgnoreCase)))
            return Results.Ok(new { status = "ya_cargado" });

        var ramUsadaPorModelos = SumarRamEstimada(modelosActivos);
        if (ramUsadaPorModelos + info.RamEstimadaMB > PRESUPUESTO_TOTAL_MB)
        {
            Log($"DEBUG: presupuesto insuficiente para '{modelo}' " +
                $"({ramUsadaPorModelos}+{info.RamEstimadaMB} > {PRESUPUESTO_TOTAL_MB}); " +
                $"liberando por prioridad...");

            modelosActivos = await LiberarPorPrioridad(info);
            ramUsadaPorModelos = SumarRamEstimada(modelosActivos);

            Log($"DEBUG: tras liberar, RAM modelos={ramUsadaPorModelos}MB, " +
                $"presupuesto={PRESUPUESTO_TOTAL_MB}MB, " +
                $"necesita={info.RamEstimadaMB}MB");

            if (ramUsadaPorModelos + info.RamEstimadaMB > PRESUPUESTO_TOTAL_MB)
            {
                Log($"RECHAZADO: '{modelo}' excede presupuesto global " +
                    $"({ramUsadaPorModelos}+{info.RamEstimadaMB} > {PRESUPUESTO_TOTAL_MB} MB)");
                return Results.Ok(new
                {
                    status = "PRESUPUESTO_EXCEDIDO",
                    ramUsadaPorModelos,
                    presupuestoTotalMB = PRESUPUESTO_TOTAL_MB
                });
            }
        }

        await CargarEnOllama(modelo);
        Log($"CARGADO: '{modelo}' (~{info.RamEstimadaMB}MB, prioridad={info.Prioridad})");
        return Results.Ok(new { status = "cargado" });
    }
    finally
    {
        recursoLock.Release();
    }
});

app.MapPost("/unload/{modelo}", async (string modelo) =>
{
    await recursoLock.WaitAsync();
    try
    {
        await DescargarDeOllama(modelo);
        Log($"DESCARGADO (manual): '{modelo}'");
        return Results.Ok(new { status = "descargado" });
    }
    finally
    {
        recursoLock.Release();
    }
});

app.Lifetime.ApplicationStarted.Register(() =>
{
    Task.Run(InicializarHardwareMonitor);
});

app.Lifetime.ApplicationStopping.Register(() =>
{
    lock (hardwareLock)
    {
        hardwareComputer?.Close();
    }
});

app.Run(managerUrl);


// ---- Funciones auxiliares ----

static long ObtenerRamDisponibleMB()
{
    var status = new MEMORYSTATUSEX();
    status.dwLength = (uint)Marshal.SizeOf(status);
    GlobalMemoryStatusEx(ref status);
    return (long)(status.ullAvailPhys / (1024 * 1024));
}

async Task<List<OllamaModel>> ObtenerModelosActivosDeOllama()
{
    var respuesta = await httpClient.GetStringAsync($"{OLLAMA_URL}/api/ps");
    var data = JsonSerializer.Deserialize<OllamaPsResponse>(respuesta,
        new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
    return data?.Models ?? new List<OllamaModel>();
}

long SumarRamEstimada(List<OllamaModel> modelosActivos) =>
    SumarRamEstimadaSync(modelosActivos);

// Suma el `size` real que reporta /api/ps. Si por alguna razón llega 0,
// cae a estimación estática de models.json.
long SumarRamEstimadaSync(List<OllamaModel> modelosActivos)
{
    if (modelosActivos.Count == 0) return 0;

    long totalApiMB = modelosActivos.Sum(m => m.Size) / (1024 * 1024);
    if (totalApiMB > 0)
    {
        Log($"DEBUG: RAM de modelos (API Ollama): {totalApiMB}MB");
        return totalApiMB;
    }

    long ramRealOllama = ObtenerRamProcesoOllama();
    if (ramRealOllama > 0)
    {
        Log($"DEBUG: Usando RAM de procesos llama-server: {ramRealOllama}MB");
        return ramRealOllama;
    }

    Log($"DEBUG: Fallback a estimación estática de models.json");
    long total = 0;
    foreach (var modelo in modelosActivos)
    {
        var match = modelRegistry.Keys.FirstOrDefault(k =>
            k.Equals(modelo.Name, StringComparison.OrdinalIgnoreCase) ||
            modelo.Name.Equals(k, StringComparison.OrdinalIgnoreCase) ||
            k.Contains(modelo.Name) || modelo.Name.Contains(k)
        );

        if (match != null)
        {
            total += modelRegistry[match].RamEstimadaMB;
            Log($"DEBUG: modelo '{modelo.Name}' match con '{match}' = {modelRegistry[match].RamEstimadaMB}MB (estimado)");
        }
        else
        {
            Log($"WARN: modelo activo '{modelo.Name}' no encontrado en registry");
        }
    }

    return total;
}

long ObtenerRamProcesoOllama()
{
    try
    {
        var processes = Process.GetProcessesByName("llama-server");
        if (processes.Length == 0)
        {
            Log("DEBUG: No se encontró proceso llama-server corriendo");
            return 0;
        }

        long totalMB = 0;
        int contados = 0;
        foreach (var p in processes)
        {
            try
            {
                long mb = p.WorkingSet64 / (1024 * 1024);
                totalMB += mb;
                contados++;
                Log($"DEBUG: llama-server PID {p.Id} → {mb}MB");
            }
            catch (Exception ex)
            {
                Log($"WARN: no pude leer PID {p.Id}: {ex.Message}");
            }
        }
        Log($"DEBUG: llama-server TOTAL → {totalMB}MB ({contados} proceso(s))");
        return totalMB;
    }
    catch (Exception ex)
    {
        Log($"WARN: No se pudo obtener RAM del proceso llama-server: {ex.GetType().Name} - {ex.Message}");
        return 0;
    }
}

// === FIX CRÍTICO v5: semántica de prioridad + modelos no registrados ===
//
// Semántica: prioridad MÁS BAJA = MÁS PRESCINDIBLE = se descarga primero.
// Orden ascendente: 1, 2, 3, 4… así el chat (prioridad 1) cae antes
// que el coder (prioridad 3).
//
// Modelos activos que NO estén en el registry se tratan como prioridad
// int.MinValue (los primeros en descargarse). Antes eran ignorados por
// el .Where(x => x.Clave != null) y nunca se descargaban.
//
// Refetch del estado real antes de cada descarga para evitar decisiones
// con datos obsoletos.
async Task<List<OllamaModel>> LiberarPorPrioridad(ModelInfo infoNuevo)
{
    string? ResolverClave(string nombreOllama)
    {
        // 1) Match EXACTO primero (case-insensitive)
        foreach (var k in modelRegistry.Keys)
        {
            if (k.Equals(nombreOllama, StringComparison.OrdinalIgnoreCase))
                return k;
        }
        // 2) Match por contención (fallback)
        foreach (var k in modelRegistry.Keys)
        {
            if (k.Contains(nombreOllama, StringComparison.OrdinalIgnoreCase) ||
                nombreOllama.Contains(k, StringComparison.OrdinalIgnoreCase))
                return k;
        }
        return null;
    }

    var modelosActivos = await ObtenerModelosActivosDeOllama();

    // Incluir TODOS los activos como candidatos, no solo los que
    // resuelven a una clave del registry.
    var candidatos = modelosActivos
        .Select(m =>
        {
            var clave = ResolverClave(m.Name);
            var prioridad = clave != null
                ? modelRegistry[clave].Prioridad
                : int.MinValue;   // desconocido -> primero en caer
            return new { Modelo = m, Clave = clave, Prioridad = prioridad };
        })
        .OrderBy(x => x.Prioridad)   // <-- ASCENDENTE: prioridad baja = cae primero
        .ToList();

    Log($"DEBUG: LiberarPorPrioridad — {candidatos.Count} candidato(s) de {modelosActivos.Count} activo(s)");
    foreach (var c in candidatos)
    {
        Log($"DEBUG:   candidato '{c.Modelo.Name}' " +
            $"(clave={c.Clave ?? "?"}, prioridad={c.Prioridad})");
    }

    foreach (var c in candidatos)
    {
        // Refetch del estado real antes de decidir
        modelosActivos = await ObtenerModelosActivosDeOllama();
        long ramActual = SumarRamEstimadaSync(modelosActivos);

        if (PRESUPUESTO_TOTAL_MB - ramActual >= infoNuevo.RamEstimadaMB)
        {
            Log($"DEBUG: presupuesto ya alcanza " +
                $"({ramActual}+{infoNuevo.RamEstimadaMB} <= {PRESUPUESTO_TOTAL_MB}), paro de liberar");
            break;
        }

        // ¿Sigue activo? Pudiera haberse descargado ya
        bool sigueActivo = modelosActivos.Any(m =>
            m.Name.Equals(c.Modelo.Name, StringComparison.OrdinalIgnoreCase));
        if (!sigueActivo)
        {
            Log($"DEBUG: '{c.Modelo.Name}' ya no estaba activo, salto");
            continue;
        }

        Log($"DEBUG: descargando '{c.Modelo.Name}' (prioridad {c.Prioridad})...");
        await DescargarDeOllama(c.Modelo.Name);
        Log($"DESCARGADO (auto, por prioridad): '{c.Modelo.Name}' " +
            $"(prioridad {c.Prioridad})");

        // Dar tiempo a Ollama a soltar la RAM antes del siguiente refetch
        await Task.Delay(600);
    }

    return await ObtenerModelosActivosDeOllama();
}

async Task CargarEnOllama(string modelo)
{
    var payload = JsonSerializer.Serialize(new
    {
        model = modelo,
        prompt = "",
        keep_alive = managerModelKeepAlive
    });
    await httpClient.PostAsync($"{OLLAMA_URL}/api/generate",
        new StringContent(payload, System.Text.Encoding.UTF8, "application/json"));
}

// === FIX v5: leer el body de la respuesta ===
// PostAsync solo espera las cabeceras, no consume el body. Sin leerlo, la
// conexión queda a medias y Ollama puede tardar en liberar el modelo.
async Task DescargarDeOllama(string modelo)
{
    try
    {
        var payload = JsonSerializer.Serialize(new
        {
            model = modelo,
            prompt = "",
            keep_alive = 0
        });
        var resp = await httpClient.PostAsync(
            $"{OLLAMA_URL}/api/generate",
            new StringContent(payload, System.Text.Encoding.UTF8, "application/json"));

        // Leer el body SIEMPRE
        var body = await resp.Content.ReadAsStringAsync();

        if (!resp.IsSuccessStatusCode)
        {
            var fragmento = body.Length > 200 ? body.Substring(0, 200) : body;
            Log($"WARN: DescargarDeOllama('{modelo}') HTTP " +
                $"{(int)resp.StatusCode}: {fragmento}");
        }
    }
    catch (Exception ex)
    {
        Log($"WARN: DescargarDeOllama('{modelo}') lanzó " +
            $"{ex.GetType().Name}: {ex.Message}");
    }
}

[DllImport("kernel32.dll")]
static extern bool GlobalMemoryStatusEx(ref MEMORYSTATUSEX lpBuffer);

[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
struct MEMORYSTATUSEX
{
    public uint dwLength;
    public uint dwMemoryLoad;
    public ulong ullTotalPhys;
    public ulong ullAvailPhys;
    public ulong ullTotalPageFile;
    public ulong ullAvailPageFile;
    public ulong ullTotalVirtual;
    public ulong ullAvailVirtual;
    public ulong ullAvailExtendedVirtual;
}

class CpuUsageCounter
{
    private ulong _lastIdle;
    private ulong _lastKernel;
    private ulong _lastUser;

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetSystemTimes(out FILETIME lpIdleTime, out FILETIME lpKernelTime, out FILETIME lpUserTime);

    [StructLayout(LayoutKind.Sequential)]
    private struct FILETIME
    {
        public uint dwLowDateTime;
        public uint dwHighDateTime;
        public ulong ToULong() => ((ulong)dwHighDateTime << 32) | dwLowDateTime;
    }

    public CpuUsageCounter()
    {
        if (GetSystemTimes(out var idle, out var kernel, out var user))
        {
            _lastIdle = idle.ToULong();
            _lastKernel = kernel.ToULong();
            _lastUser = user.ToULong();
        }
    }

    public double NextValue()
    {
        if (!GetSystemTimes(out var idle, out var kernel, out var user))
            return 0.0;

        ulong idleNow = idle.ToULong();
        ulong kernelNow = kernel.ToULong();
        ulong userNow = user.ToULong();

        ulong idleDelta = idleNow - _lastIdle;
        ulong kernelDelta = kernelNow - _lastKernel;
        ulong userDelta = userNow - _lastUser;

        _lastIdle = idleNow;
        _lastKernel = kernelNow;
        _lastUser = userNow;

        ulong total = kernelDelta + userDelta;
        if (total == 0) return 0.0;

        ulong busy = total - idleDelta;
        return 100.0 * busy / total;
    }
}

record ModelInfo
{
    [JsonPropertyName("ramEstimadaMB")]
    public long RamEstimadaMB { get; init; }

    [JsonPropertyName("prioridad")]
    public int Prioridad { get; init; }
}

record OllamaModel
{
    public string Name { get; init; } = "";
    public long Size { get; init; } = 0;
}

record OllamaPsResponse
{
    public List<OllamaModel> Models { get; init; } = new();
}
