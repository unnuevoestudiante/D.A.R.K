using DarkTaskManager.Services;
using DarkTaskManager.Models;
using DarkTaskManager.DTOs;

var builder = WebApplication.CreateBuilder(args);

// Configurar serialización JSON para usar strings en lugar de números para enums
builder.Services.ConfigureHttpJsonOptions(options =>
{
    options.SerializerOptions.Converters.Add(new System.Text.Json.Serialization.JsonStringEnumConverter());
});

// Configurar como Windows Service (LocalSystem)
builder.Host.UseWindowsService(options =>
{
    options.ServiceName = "DARK Task Manager";
});

var app = builder.Build();

var runtimeConfigPath = Environment.GetEnvironmentVariable("DARK_RUNTIME_CONFIG")
    ?? Path.Combine(AppContext.BaseDirectory, "runtime.json");
using var runtimeConfig = System.Text.Json.JsonDocument.Parse(File.ReadAllText(runtimeConfigPath));
var taskManagerUrl = runtimeConfig.RootElement.GetProperty("services")
    .GetProperty("taskManager").GetProperty("url").GetString()
    ?? throw new InvalidDataException("services.taskManager.url vacío en runtime.json");
var managerUrl = runtimeConfig.RootElement.GetProperty("services")
    .GetProperty("manager").GetProperty("url").GetString()
    ?? throw new InvalidDataException("services.manager.url vacío en runtime.json");

// Anclar rutas al directorio del .exe (importante para Windows Service)
var baseDir = Environment.GetEnvironmentVariable("DARK_USER_DATA_DIR") is { Length: > 0 } dataDirectory
    ? Path.GetFullPath(dataDirectory)
    : AppContext.BaseDirectory;
var logsDir = Environment.GetEnvironmentVariable("DARK_USER_LOG_DIR") is { Length: > 0 } configuredLogs
    ? Path.GetFullPath(configuredLogs)
    : baseDir;
Directory.CreateDirectory(baseDir);
Directory.CreateDirectory(logsDir);

// Inicializar Task Manager
var taskPersistence = new TaskPersistence(baseDir);
var httpClient = new HttpClient();
var taskManager = new TaskManager(taskPersistence, httpClient, baseDir, managerUrl, logsDir);

// --- Endpoints del Task Manager ---

// GET /tasks - Listar todas las tareas
app.MapGet("/tasks", () =>
{
    return Results.Ok(taskManager.ObtenerTodas());
});

// GET /tasks/{id} - Obtener una tarea específica
app.MapGet("/tasks/{id}", (string id) =>
{
    var tarea = taskManager.ObtenerTarea(id);
    if (tarea is null)
        return Results.NotFound(new { error = $"Tarea {id} no encontrada" });
    return Results.Ok(tarea);
});

// GET /tasks/status/{estado} - Filtrar tareas por estado
app.MapGet("/tasks/status/{estado}", (string estado) =>
{
    if (!Enum.TryParse<DarkTaskStatus>(estado, true, out var estadoEnum))
        return Results.BadRequest(new { error = $"Estado '{estado}' no válido" });
    
    return Results.Ok(taskManager.ObtenerPorEstado(estadoEnum));
});

// GET /tasks/interrupted - Listar tareas interrumpidas
app.MapGet("/tasks/interrupted", () =>
{
    return Results.Ok(taskManager.ObtenerTareasIncompletas());
});

// POST /tasks - Crear una nueva tarea
app.MapPost("/tasks", (TaskRequest request) =>
{
    var taskId = taskManager.CrearTarea(
        request.Descripcion,
        request.Prioridad,
        request.Modulo
    );
    
    // Si se enviaron pasos iniciales, agregarlos
    if (request.Pasos?.Any() == true)
    {
        var pasos = request.Pasos.Select(p => new TaskStep
        {
            Id = p.Id,
            Descripcion = p.Descripcion
        }).ToList();
        taskManager.AgregarPasos(taskId, pasos);
    }
    
    return Results.Ok(new { id = taskId });
});

// POST /tasks/{id}/start - Iniciar una tarea
app.MapPost("/tasks/{id}/start", async (string id) =>
{
    var iniciada = await taskManager.IniciarTarea(id);
    if (!iniciada)
        return Results.BadRequest(new { error = "No se pudo iniciar la tarea (dependencias o recursos insuficientes)" });
    return Results.Ok(new { status = "iniciada" });
});

// POST /tasks/{id}/pause - Pausar una tarea
app.MapPost("/tasks/{id}/pause", (string id) =>
{
    taskManager.PausarTarea(id);
    return Results.Ok(new { status = "pausada" });
});

// POST /tasks/{id}/cancel - Cancelar una tarea
app.MapPost("/tasks/{id}/cancel", (string id) =>
{
    taskManager.CancelarTarea(id);
    return Results.Ok(new { status = "cancelada" });
});

// POST /tasks/{id}/resume - Reanudar una tarea interrumpida
app.MapPost("/tasks/{id}/resume", async (string id) =>
{
    var resultado = await taskManager.ReanudarTarea(id);
    if (resultado is null)
        return Results.NotFound(new { error = "Tarea no encontrada" });
    return Results.Ok(resultado);
});

// POST /tasks/{id}/steps - Agregar pasos a una tarea existente
app.MapPost("/tasks/{id}/steps", (string id, AgregarPasosRequest request) =>
{
    try
    {
        var pasos = request.Pasos.Select(p => new TaskStep
        {
            Id = p.Id,
            Descripcion = p.Descripcion
        }).ToList();

        taskManager.AgregarPasos(id, pasos);
        return Results.Ok(new { status = "pasos_agregados", count = pasos.Count });
    }
    catch (ArgumentException ex)
    {
        return Results.NotFound(new { error = ex.Message });
    }
});

// POST /tasks/{id}/steps/{stepId}/complete - Marcar un paso como completado
app.MapPost("/tasks/{id}/steps/{stepId}/complete", (string id, string stepId, StepCompleteRequest? request) =>
{
    taskManager.CompletarPaso(id, stepId, request?.Resultado);
    return Results.Ok(new { status = "paso_completado" });
});

// POST /tasks/{id}/steps/{stepId}/fail - Marcar un paso como fallido
app.MapPost("/tasks/{id}/steps/{stepId}/fail", (string id, string stepId, StepFailRequest request) =>
{
    taskManager.FallarPaso(id, stepId, request.Error);
    return Results.Ok(new { status = "paso_fallido" });
});

// POST /tasks/{id}/steps/{stepId}/retry - Reintentar un paso fallido
app.MapPost("/tasks/{id}/steps/{stepId}/retry", async (string id, string stepId) =>
{
    var reintentado = await taskManager.ReintentarPaso(id, stepId);
    if (!reintentado)
        return Results.NotFound(new { error = "Paso o tarea no encontrados" });
    return Results.Ok(new { status = "reintentado" });
});

// POST /tasks/{id}/complete - Marcar tarea como completada
app.MapPost("/tasks/{id}/complete", (string id, TaskCompleteRequest request) =>
{
    taskManager.CompletarTarea(id, request.Resultado);
    return Results.Ok(new { status = "completada" });
});

// POST /tasks/{id}/fail - Marcar tarea como fallida
app.MapPost("/tasks/{id}/fail", (string id, TaskFailRequest request) =>
{
    taskManager.FallarTarea(id, request.Razon);
    return Results.Ok(new { status = "fallida" });
});

app.Run(taskManagerUrl);

namespace DarkTaskManager.DTOs
{
    public record TaskRequest
    {
        public required string Descripcion { get; init; }
        public TaskPriority Prioridad { get; init; } = TaskPriority.Normal;
        public TaskModule Modulo { get; init; } = TaskModule.Nucleo;
        public List<StepRequest>? Pasos { get; init; }
    }

    public record StepRequest
    {
        public required string Id { get; init; }
        public required string Descripcion { get; init; }
    }

    public record StepCompleteRequest
    {
        public string? Resultado { get; init; }
    }

    public record StepFailRequest
    {
        public required string Error { get; init; }
    }

    public record TaskCompleteRequest
    {
        public required string Resultado { get; init; }
    }

    public record TaskFailRequest
    {
        public required string Razon { get; init; }
    }

    // NUEVO: request para agregar pasos dinámicamente a una tarea existente
    public record AgregarPasosRequest
    {
        public required List<StepRequest> Pasos { get; init; }
    }
}
