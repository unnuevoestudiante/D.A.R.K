using System.Text.Json.Serialization;

namespace DarkTaskManager.Models;




// Estado de una tarea - coincide con tu especificación
[JsonConverter(typeof(JsonStringEnumConverter))]
public enum DarkTaskStatus
{
    Pendiente,           // Creada pero no iniciada
    Ejecutandose,        // En progreso actualmente
    Pausada,             // Detenida temporalmente (por usuario o sistema)
    Completada,          // Terminó exitosamente
    Fallida,             // Terminó con error irrecuperable
    Cancelada,           // Cancelada explícitamente por usuario
    RequiereConfirmacion // Necesita aprobación antes de continuar
}



// Prioridad de una tarea (número más alto = más urgente)
[JsonConverter(typeof(JsonStringEnumConverter))]
public enum TaskPriority
{
    Baja = 1,
    Normal = 2,
    Alta = 3,
    Critica = 4
}

// Módulo asignado a la tarea (extensible para futuros módulos)
[JsonConverter(typeof(JsonStringEnumConverter))]
public enum TaskModule
{
    Nucleo,      // El núcleo central de D.A.R.K
    Telefono,    // Module 2 (en desarrollo)
    Desconocido  // Para compatibilidad con módulos futuros
}


// Un paso/checkpoint individual dentro de una tarea
public class TaskStep
{
    public required string Id { get; init; }           // ID único del paso (ej: "crear-archivo-html")
    public required string Descripcion { get; init; } // Qué hace este paso
    public bool Completado { get; set; }               // Si ya se ejecutó
    public DateTime? CompletadoEn { get; set; }       // Cuándo se completó
    public string? Resultado { get; set; }            // Resultado parcial (ej: ruta del archivo creado)
    public string? Error { get; set; }                // Error si falló este paso específico
    public int Intentos { get; set; } = 0;            // Cuántas veces se intentó este paso
}

// Estado de recursos/herramientas usados por una tarea en un momento dado
public class TaskResourceSnapshot
{
    public required DateTime Timestamp { get; init; }          // Cuándo se tomó el snapshot
    public long? RamDisponibleMB { get; init; }                 // RAM disponible en ese momento
    public double? CpuUsoPct { get; init; }                     // % de CPU en ese momento
    public Dictionary<string, object> EstadoHerramientas { get; init; } = new(); // Estado específico de cada herramienta (ej: "ollama": "qwen3:4b-instruct cargado")
}

// Tarea principal
public class DarkTask
{
    public required string Id { get; init; }                   // GUID único
    public required string Descripcion { get; init; }          // Qué hace la tarea
    public DarkTaskStatus Estado { get; set; } = DarkTaskStatus.Pendiente;
    public TaskPriority Prioridad { get; set; } = TaskPriority.Normal;
    public TaskModule ModuloAsignado { get; set; } = TaskModule.Nucleo;
    
    public DateTime FechaCreacion { get; init; } = DateTime.UtcNow;
    public DateTime? FechaUltimaActualizacion { get; set; }
    public DateTime? FechaCompletacion { get; set; }
    
    // Progreso granular: lista de pasos/checkpoints
    public List<TaskStep> Pasos { get; init; } = new();
    
    // Cuál paso está actualmente en ejecución (null si no está ejecutándose)
    public string? PasoActualId { get; set; }
    
    // Dependencias: IDs de tareas que deben completarse antes de esta
    public List<string> Dependencias { get; init; } = new();
    
    // Resultado final de la tarea
    public string? ResultadoFinal { get; set; }
    
    // Errores acumulados de la tarea completa
    public List<string> Errores { get; init; } = new();
    
    // Snapshot de recursos antes de iniciar la tarea
    public TaskResourceSnapshot? SnapshotInicial { get; set; }
    
    // Snapshot de recursos actual (se actualiza en cada checkpoint)
    public TaskResourceSnapshot? SnapshotActual { get; set; }
    
    // Metadata adicional (extensible)
    public Dictionary<string, string> Metadata { get; init; } = new();
    
    // Para rollback: guardamos snapshots antes de cada acción destructiva
    public List<TaskResourceSnapshot> SnapshotsParaRollback { get; init; } = new();
}
