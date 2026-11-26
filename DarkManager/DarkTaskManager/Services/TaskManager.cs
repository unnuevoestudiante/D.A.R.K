using System.Text.Json;
using DarkTaskManager.Models;

namespace DarkTaskManager.Services;

// Struct para ordenar la cola por prioridad y luego por tiempo de creación (FIFO)
public struct PriorityTuple : IComparable<PriorityTuple>
{
    public int Priority { get; }
    public long Timestamp { get; }

    public PriorityTuple(int priority, long timestamp)
    {
        Priority = priority;
        Timestamp = timestamp;
    }

    public int CompareTo(PriorityTuple other)
    {
        // Primero por prioridad (mayor número = mayor prioridad)
        int priorityComparison = other.Priority.CompareTo(Priority);
        if (priorityComparison != 0)
            return priorityComparison;
        
        // Si misma prioridad, por timestamp (más antiguo primero = FIFO)
        return Timestamp.CompareTo(other.Timestamp);
    }
}

public class TaskManager
{
    private readonly TaskPersistence _persistence;
    private readonly HttpClient _httpClient;
    private readonly string _logPath;
    private readonly string _managerUrl;
    
    // Estado en memoria de las tareas (se sincroniza con disco en cada cambio)
    private Dictionary<string, DarkTask> _tareas = new();
    
    // Cola de tareas pendientes ordenadas por prioridad y tiempo de creación
    private PriorityQueue<string, PriorityTuple> _colaPendientes = new();
    
    // Lock global para serializar todas las mutaciones del diccionario
    // _tareas y de las listas internas de cada DarkTask. Un solo lock
    // granular por operación evita el patrón de doble adquisición que
    // provocaría deadlocks si se anidaran.
    private readonly object _lock = new();
    
    // Evento para notificar cambios de estado (para endpoints de polling si lo necesitas más adelante)
    public event Action<string, DarkTask>? OnTaskStateChanged;

    public TaskManager(TaskPersistence persistence, HttpClient httpClient, string baseDir, string managerUrl, string? logsDir = null)
    {
        _persistence = persistence;
        _httpClient = httpClient;
        _logPath = Path.Combine(logsDir ?? baseDir, "task-manager.log");
        _managerUrl = managerUrl.TrimEnd('/');
        
        // Cargar tareas existentes desde disco al iniciar
        _tareas = _persistence.CargarTodas();
        DetectarTareasIncompletas();
        ReconstruirCola();
        
        Log("TaskManager inicializado. Tareas cargadas desde disco: " + _tareas.Count);
    }

    // Detectar tareas incompletas al iniciar (CRÍTICO para el escenario Einstein)
    private void DetectarTareasIncompletas()
    {
        var tareasIncompletas = _tareas.Values
            .Where(t => t.Estado == DarkTaskStatus.Ejecutandose || t.Estado == DarkTaskStatus.Pausada)
            .ToList();
        
        if (tareasIncompletas.Any())
        {
            Log($"DETECTADAS {tareasIncompletas.Count} TAREAS INCOMPLETAS AL INICIAR:");
            foreach (var tarea in tareasIncompletas)
            {
                // Marcar como RequiereConfirmacion para que el usuario decida qué hacer
                tarea.Estado = DarkTaskStatus.RequiereConfirmacion;
                tarea.Metadata["interrumpida_al_inicio"] = "true";
                tarea.FechaUltimaActualizacion = DateTime.UtcNow;
                
                var ultimoPasoCompletado = tarea.Pasos
                    .Where(p => p.Completado)
                    .OrderByDescending(p => p.CompletadoEn)
                    .FirstOrDefault();
                
                var contexto = ultimoPasoCompletado != null
                    ? $"Último paso completado: {ultimoPasoCompletado.Id} ({ultimoPasoCompletado.Descripcion})"
                    : "Sin pasos completados";
                
                Log($"  - Tarea {tarea.Id}: {tarea.Descripcion} | {contexto} | {tarea.Pasos.Count(p => p.Completado)}/{tarea.Pasos.Count} pasos completados");
                
                _persistence.GuardarUna(tarea);
            }
        }
    }

    // Crear una nueva tarea
    public string CrearTarea(string descripcion, TaskPriority prioridad = TaskPriority.Normal, TaskModule modulo = TaskModule.Nucleo)
    {
        var tarea = new DarkTask
        {
            Id = Guid.NewGuid().ToString(),
            Descripcion = descripcion,
            Prioridad = prioridad,
            ModuloAsignado = modulo,
            Estado = DarkTaskStatus.Pendiente
        };
        
        lock (_lock)
        {
            _tareas[tarea.Id] = tarea;
        }
        
        _persistence.GuardarUna(tarea);
        
        // Agregar a la cola de pendientes con timestamp para FIFO
        lock (_lock)
        {
            _colaPendientes.Enqueue(tarea.Id, new PriorityTuple((int)prioridad, DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()));
        }
        
        Log($"TAREA CREADA: {tarea.Id} - {descripcion} (Prioridad: {prioridad})");
        OnTaskStateChanged?.Invoke(tarea.Id, tarea);
        
        return tarea.Id;
    }

    // Agregar pasos a una tarea existente
    // Este método es thread-safe: toma el lock solo para mutar estado en
    // memoria, y hace I/O y notificaciones fuera del lock.
    public void AgregarPasos(string taskId, List<TaskStep> pasos)
    {
        DarkTask tarea;
        lock (_lock)
        {
            if (!_tareas.ContainsKey(taskId))
                throw new ArgumentException($"Tarea {taskId} no existe");
            
            tarea = _tareas[taskId];
            tarea.Pasos.AddRange(pasos);
            tarea.FechaUltimaActualizacion = DateTime.UtcNow;
        }
        
        _persistence.GuardarUna(tarea);
        Log($"PASOS AGREGADOS: {taskId} ({pasos.Count} pasos, total ahora {tarea.Pasos.Count})");
        
        // Si la tarea estaba en Pendiente, reconstruir la cola con el nuevo timestamp
        if (tarea.Estado == DarkTaskStatus.Pendiente)
        {
            ReconstruirCola();
        }
    }

    // Iniciar ejecución de una tarea
    public async Task<bool> IniciarTarea(string taskId)
    {
        DarkTask? tarea;
        lock (_lock)
        {
            if (!_tareas.ContainsKey(taskId))
                return false;
            tarea = _tareas[taskId];
        }
        
        // Verificar dependencias
        if (!DependenciasCumplidas(tarea))
        {
            lock (_lock)
            {
                tarea.Estado = DarkTaskStatus.Pendiente;
            }
            Log($"TAREA BLOQUEADA POR DEPENDENCIAS: {taskId}");
            _persistence.GuardarUna(tarea);
            return false;
        }
        
        // Verificar recursos disponibles antes de iniciar
        if (!await RecursosSuficientes())
        {
            lock (_lock)
            {
                tarea.Estado = DarkTaskStatus.Pendiente;
            }
            Log($"TAREA BLOQUEADA POR RECURSOS: {taskId}");
            _persistence.GuardarUna(tarea);
            return false;
        }
        
        // Tomar snapshot inicial de recursos
        var snapshot = await TomarSnapshotRecursos();
        lock (_lock)
        {
            tarea.SnapshotInicial = snapshot;
            tarea.Estado = DarkTaskStatus.Ejecutandose;
            tarea.FechaUltimaActualizacion = DateTime.UtcNow;
        }
        
        _persistence.GuardarUna(tarea);
        Log($"TAREA INICIADA: {taskId}");
        OnTaskStateChanged?.Invoke(taskId, tarea);
        
        return true;
    }

    // Marcar un paso como completado (ESCRIBE A DISCO INMEDIATAMENTE)
    public void CompletarPaso(string taskId, string pasoId, string? resultado = null)
    {
        DarkTask tarea;
        TaskStep? paso;
        lock (_lock)
        {
            if (!_tareas.ContainsKey(taskId))
                throw new ArgumentException($"Tarea {taskId} no existe");
            
            tarea = _tareas[taskId];
            paso = tarea.Pasos.FirstOrDefault(p => p.Id == pasoId);
            
            if (paso is null)
                throw new ArgumentException($"Paso {pasoId} no existe en tarea {taskId}");
            
            paso.Completado = true;
            paso.CompletadoEn = DateTime.UtcNow;
            paso.Resultado = resultado;
            paso.Intentos++;
            
            tarea.PasoActualId = null; // Ya no hay paso actual
            tarea.FechaUltimaActualizacion = DateTime.UtcNow;
        }
        
        // Actualizar snapshot de recursos (fuera del lock)
        _ = TomarSnapshotRecursosAsync(tarea);
        
        _persistence.GuardarUna(tarea);
        Log($"PASO COMPLETADO: {taskId}/{pasoId} - {paso.Descripcion}");
        OnTaskStateChanged?.Invoke(taskId, tarea);
    }

    // Marcar un paso como fallido (ESCRIBE A DISCO INMEDIATAMENTE)
    public void FallarPaso(string taskId, string pasoId, string error)
    {
        DarkTask tarea;
        TaskStep? paso;
        lock (_lock)
        {
            if (!_tareas.ContainsKey(taskId))
                throw new ArgumentException($"Tarea {taskId} no existe");
            
            tarea = _tareas[taskId];
            paso = tarea.Pasos.FirstOrDefault(p => p.Id == pasoId);
            
            if (paso is null)
                throw new ArgumentException($"Paso {pasoId} no existe en tarea {taskId}");
            
            paso.Error = error;
            paso.Intentos++;
            tarea.Errores.Add($"Paso {pasoId}: {error}");
            tarea.FechaUltimaActualizacion = DateTime.UtcNow;
        }
        
        _persistence.GuardarUna(tarea);
        Log($"PASO FALLIDO: {taskId}/{pasoId} - {error}");
        OnTaskStateChanged?.Invoke(taskId, tarea);
    }

    // Reintentar un paso fallido
    public async Task<bool> ReintentarPaso(string taskId, string pasoId)
    {
        DarkTask? tarea;
        TaskStep? paso;
        lock (_lock)
        {
            if (!_tareas.ContainsKey(taskId))
                return false;
            
            tarea = _tareas[taskId];
            paso = tarea.Pasos.FirstOrDefault(p => p.Id == pasoId);
            
            if (paso is null)
                return false;
            
            // Reiniciar estado del paso
            paso.Error = null;
            paso.Completado = false;
            tarea.PasoActualId = pasoId;
            tarea.FechaUltimaActualizacion = DateTime.UtcNow;
        }
        
        _persistence.GuardarUna(tarea);
        Log($"REINTENTO PUESTO EN COLA: {taskId}/{pasoId}");
        
        return true;
    }

    // Marcar tarea como completada
    public void CompletarTarea(string taskId, string resultadoFinal)
    {
        DarkTask tarea;
        lock (_lock)
        {
            if (!_tareas.ContainsKey(taskId))
                throw new ArgumentException($"Tarea {taskId} no existe");
            
            tarea = _tareas[taskId];
            tarea.Estado = DarkTaskStatus.Completada;
            tarea.ResultadoFinal = resultadoFinal;
            tarea.FechaCompletacion = DateTime.UtcNow;
            tarea.FechaUltimaActualizacion = DateTime.UtcNow;
            tarea.PasoActualId = null;
        }
        
        _persistence.GuardarUna(tarea);
        Log($"TAREA COMPLETADA: {taskId} - {resultadoFinal}");
        OnTaskStateChanged?.Invoke(taskId, tarea);
    }

    // Marcar tarea como fallida
    public void FallarTarea(string taskId, string razon)
    {
        DarkTask tarea;
        lock (_lock)
        {
            if (!_tareas.ContainsKey(taskId))
                throw new ArgumentException($"Tarea {taskId} no existe");
            
            tarea = _tareas[taskId];
            tarea.Estado = DarkTaskStatus.Fallida;
            tarea.Errores.Add(razon);
            tarea.FechaUltimaActualizacion = DateTime.UtcNow;
            tarea.PasoActualId = null;
        }
        
        _persistence.GuardarUna(tarea);
        Log($"TAREA FALLIDA: {taskId} - {razon}");
        OnTaskStateChanged?.Invoke(taskId, tarea);
    }

    // Pausar una tarea en ejecución
    public void PausarTarea(string taskId)
    {
        DarkTask? tarea;
        lock (_lock)
        {
            if (!_tareas.ContainsKey(taskId))
                throw new ArgumentException($"Tarea {taskId} no existe");
            
            tarea = _tareas[taskId];
            if (tarea.Estado != DarkTaskStatus.Ejecutandose)
                return;
            
            tarea.Estado = DarkTaskStatus.Pausada;
            tarea.FechaUltimaActualizacion = DateTime.UtcNow;
            tarea.PasoActualId = null;
        }
        
        _persistence.GuardarUna(tarea);
        Log($"TAREA PAUSADA: {taskId}");
        OnTaskStateChanged?.Invoke(taskId, tarea);
    }

    // Cancelar una tarea
    public void CancelarTarea(string taskId)
    {
        DarkTask tarea;
        lock (_lock)
        {
            if (!_tareas.ContainsKey(taskId))
                throw new ArgumentException($"Tarea {taskId} no existe");
            
            tarea = _tareas[taskId];
            tarea.Estado = DarkTaskStatus.Cancelada;
            tarea.FechaUltimaActualizacion = DateTime.UtcNow;
            tarea.PasoActualId = null;
        }
        
        // Remover de la cola de pendientes si está ahí
        ReconstruirCola();
        
        _persistence.GuardarUna(tarea);
        Log($"TAREA CANCELADA: {taskId}");
        OnTaskStateChanged?.Invoke(taskId, tarea);
    }

    // Reanudar una tarea interrumpida (CRÍTICO para el escenario Einstein)
    //
    // Este método se arregló para el caso de sub-pasos jerárquicos
    // (paso-padre, paso-padre.seccion-1, paso-padre.seccion-2, ...).
    // El bug original: FirstOrDefault(p => !p.Completado) devolvía el
    // paso PADRE porque nunca se marca completado hasta que TODA la
    // tarea termina. Eso rompía a cualquier cliente que intentara
    // reanudar en el sub-paso real (devolvía "continuarDesde: padre"
    // en vez de "continuarDesde: padre.seccion-3").
    public async Task<object?> ReanudarTarea(string taskId)
    {
        DarkTask? tarea;
        lock (_lock)
        {
            if (!_tareas.ContainsKey(taskId))
                return null;
            tarea = _tareas[taskId];
        }
        
        // Verificar recursos disponibles antes de reanudar
        if (!await RecursosSuficientes())
        {
            Log($"TAREA BLOQUEADA POR RECURSOS AL REANUDAR: {taskId}");
            return new { error = "recursos_insuficientes" };
        }
        
        // Encontrar el último paso completado
        var ultimoPasoCompletado = tarea.Pasos
            .Where(p => p.Completado)
            .OrderByDescending(p => p.CompletadoEn)
            .FirstOrDefault();
        
        // Encontrar el siguiente paso a ejecutar, prefiriendo SIEMPRE
        // el primer paso HOJA pendiente. Un paso "hoja" es aquel que no
        // tiene sub-pasos asociados (IDs que empiezan por "<suId>.").
        var pasosPendientes = tarea.Pasos.Where(p => !p.Completado).ToList();
        TaskStep? siguientePaso = null;
        foreach (var paso in pasosPendientes)
        {
            var prefijo = paso.Id + ".";
            var tieneSubPasos = tarea.Pasos.Any(p => p.Id.StartsWith(prefijo));
            if (tieneSubPasos)
            {
                // El padre aún tiene hijos pendientes: no es él quien
                // hay que ejecutar, sino el primer hijo pendiente.
                continue;
            }
            siguientePaso = paso;
            break;
        }
        siguientePaso ??= pasosPendientes.FirstOrDefault();
        
        lock (_lock)
        {
            tarea.Estado = DarkTaskStatus.Ejecutandose;
            tarea.FechaUltimaActualizacion = DateTime.UtcNow;
            
            if (siguientePaso != null)
            {
                tarea.PasoActualId = siguientePaso.Id;
            }
        }
        
        _persistence.GuardarUna(tarea);
        Log($"TAREA REANUDADA: {taskId} → continuarDesde={siguientePaso?.Id ?? "(ninguno)"}");
        OnTaskStateChanged?.Invoke(taskId, tarea);
        
        // Respuesta explícita para que el Núcleo sepa exactamente por dónde continuar
        return new
        {
            id = tarea.Id,
            descripcion = tarea.Descripcion,
            ultimoPasoCompletado = ultimoPasoCompletado?.Id,
            continuarDesde = siguientePaso?.Id,
            descripcionPaso = siguientePaso?.Descripcion,
            pasosCompletados = tarea.Pasos.Count(p => p.Completado),
            totalPasos = tarea.Pasos.Count
        };
    }

    // Obtener una tarea por ID
    public DarkTask? ObtenerTarea(string taskId)
    {
        lock (_lock)
        {
            return _tareas.TryGetValue(taskId, out var tarea) ? tarea : null;
        }
    }

    // Obtener todas las tareas
    public Dictionary<string, DarkTask> ObtenerTodas()
    {
        lock (_lock)
        {
            return new Dictionary<string, DarkTask>(_tareas);
        }
    }

    // Obtener tareas por estado
    public List<DarkTask> ObtenerPorEstado(DarkTaskStatus estado)
    {
        lock (_lock)
        {
            return _tareas.Values.Where(t => t.Estado == estado).ToList();
        }
    }

    // Obtener tareas interrumpidas específicamente
    public List<DarkTask> ObtenerTareasIncompletas()
    {
        lock (_lock)
        {
            return _tareas.Values
                .Where(t => t.Estado == DarkTaskStatus.RequiereConfirmacion || 
                           t.Estado == DarkTaskStatus.Ejecutandose || 
                           t.Estado == DarkTaskStatus.Pausada ||
                           t.Metadata.ContainsKey("interrumpida_al_inicio"))
                .ToList();
        }
    }

    // Obtener la siguiente tarea pendiente de la cola
    public string? ObtenerSiguientePendiente()
    {
        lock (_lock)
        {
            while (_colaPendientes.TryDequeue(out var taskId, out var prioridad))
            {
                if (_tareas.ContainsKey(taskId) && _tareas[taskId].Estado == DarkTaskStatus.Pendiente)
                    return taskId;
            }
            return null;
        }
    }

    // ---- Métodos privados ----

    private bool DependenciasCumplidas(DarkTask tarea)
    {
        lock (_lock)
        {
            foreach (var depId in tarea.Dependencias)
            {
                if (!_tareas.ContainsKey(depId))
                    return false;
                
                var depTarea = _tareas[depId];
                if (depTarea.Estado != DarkTaskStatus.Completada)
                    return false;
            }
            return true;
        }
    }

    private async Task<bool> RecursosSuficientes()
    {
        try
        {
            // Consultar el Gestor de Recursos existente
            var respuesta = await _httpClient.GetStringAsync($"{_managerUrl}/status");
            var status = JsonSerializer.Deserialize<JsonElement>(respuesta);
            
            var ramDisponible = status.GetProperty("ramDisponibleMB").GetInt64();
            var presupuestoRestante = status.GetProperty("presupuestoRestanteMB").GetInt64();
            
            // Regla simple: al menos 2GB libres para iniciar una tarea
            return ramDisponible > 2000 && presupuestoRestante > 2000;
        }
        catch
        {
            // Si el Gestor de Recursos no responde, asumimos que no hay suficientes
            return false;
        }
    }

    private async Task<TaskResourceSnapshot> TomarSnapshotRecursos()
    {
        try
        {
            var respuesta = await _httpClient.GetStringAsync($"{_managerUrl}/status");
            var status = JsonSerializer.Deserialize<JsonElement>(respuesta);
            
            return new TaskResourceSnapshot
            {
                Timestamp = DateTime.UtcNow,
                RamDisponibleMB = status.GetProperty("ramDisponibleMB").GetInt64(),
                CpuUsoPct = status.GetProperty("cpuUsoPct").GetDouble(),
                EstadoHerramientas = new Dictionary<string, object>
                {
                    ["ollama"] = status.GetProperty("ollamaDisponible").GetBoolean()
                }
            };
        }
        catch
        {
            return new TaskResourceSnapshot
            {
                Timestamp = DateTime.UtcNow,
                RamDisponibleMB = null,
                CpuUsoPct = null,
                EstadoHerramientas = new Dictionary<string, object>()
            };
        }
    }

    private async Task TomarSnapshotRecursosAsync(DarkTask tarea)
    {
        var snapshot = await TomarSnapshotRecursos();
        lock (_lock)
        {
            tarea.SnapshotActual = snapshot;
        }
        _persistence.GuardarUna(tarea);
    }

    private void ReconstruirCola()
    {
        lock (_lock)
        {
            _colaPendientes = new PriorityQueue<string, PriorityTuple>();
            foreach (var (id, tarea) in _tareas)
            {
                if (tarea.Estado == DarkTaskStatus.Pendiente)
                {
                    // Usar timestamp de creación para FIFO dentro de cada prioridad
                    var timestamp = new DateTimeOffset(tarea.FechaCreacion).ToUnixTimeMilliseconds();
                    _colaPendientes.Enqueue(id, new PriorityTuple((int)tarea.Prioridad, timestamp));
                }
            }
        }
    }

    private void Log(string mensaje)
    {
        var linea = $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {mensaje}";
        File.AppendAllText(_logPath, linea + Environment.NewLine);
        Console.WriteLine(linea);
    }
}
