using System.Text.Json;
using DarkTaskManager.Models;

namespace DarkTaskManager.Services;

public class TaskPersistence
{
    private readonly string _tasksJsonPath;
    private readonly SemaphoreSlim _fileLock = new(1, 1);
    private readonly JsonSerializerOptions _jsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = true
    };
    private int _escrituraContador = 0;

    public TaskPersistence(string baseDir)
    {
        _tasksJsonPath = Path.Combine(baseDir, "tasks.json");
    }

    // Cargar todas las tareas desde disco (adquiere lock)
    public Dictionary<string, DarkTask> CargarTodas()
    {
        _fileLock.Wait();
        try
        {
            return CargarTodasInterno();
        }
        finally
        {
            _fileLock.Release();
        }
    }

    // Cargar todas las tareas desde disco (NO adquiere lock - para uso interno cuando ya tenemos el lock)
    private Dictionary<string, DarkTask> CargarTodasInterno()
    {
        if (!File.Exists(_tasksJsonPath))
            return new Dictionary<string, DarkTask>();

        try
        {
            var json = File.ReadAllText(_tasksJsonPath);
            var tareas = JsonSerializer.Deserialize<Dictionary<string, DarkTask>>(json, _jsonOptions);
            return tareas ?? new Dictionary<string, DarkTask>();
        }
        catch (JsonException ex)
        {
            // Si el JSON está corrupto, no debería fallar todo el servicio
            // Devolvemos un diccionario vacío y logueamos el error
            Console.WriteLine($"[TaskPersistence] Error al leer tasks.json: {ex.Message}");
            return new Dictionary<string, DarkTask>();
        }
    }

    // Guardar todas las tareas a disco con escritura atómica (adquiere lock)
    public void GuardarTodas(Dictionary<string, DarkTask> tareas)
    {
        _fileLock.Wait();
        try
        {
            GuardarTodasInterno(tareas);
        }
        finally
        {
            _fileLock.Release();
        }
    }

    // Guardar todas las tareas a disco con escritura atómica (NO adquiere lock - para uso interno)
    private void GuardarTodasInterno(Dictionary<string, DarkTask> tareas)
    {
        // TODO: si tasks.json crece mucho, migrar a un archivo por tarea o a SQLite
        // para evitar reescribir el archivo completo en cada paso.
        
        var json = JsonSerializer.Serialize(tareas, _jsonOptions);
        var tempPath = _tasksJsonPath + ".tmp";
        
        // Escribir a archivo temporal primero (escritura atómica)
        File.WriteAllText(tempPath, json);
        
        // Renombrar a archivo final (operación atómica en Windows)
        File.Move(tempPath, _tasksJsonPath, overwrite: true);
        
        _escrituraContador++;
        
        // Crear backup cada 10 escrituras
        if (_escrituraContador % 10 == 0)
        {
            CrearBackup();
        }
    }

    // Guardar una sola tarea (carga todo, modifica, guarda todo)
    public void GuardarUna(DarkTask tarea)
    {
        _fileLock.Wait();
        try
        {
            var todas = CargarTodasInterno();
            todas[tarea.Id] = tarea;
            GuardarTodasInterno(todas);
        }
        finally
        {
            _fileLock.Release();
        }
    }

    // Eliminar una tarea del archivo
    public void Eliminar(string taskId)
    {
        _fileLock.Wait();
        try
        {
            var todas = CargarTodasInterno();
            todas.Remove(taskId);
            GuardarTodasInterno(todas);
        }
        finally
        {
            _fileLock.Release();
        }
    }

    // Crear backup del archivo actual (para rollback de estado)
    private void CrearBackup()
    {
        if (!File.Exists(_tasksJsonPath))
            return;

        var timestamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
        var backupPath = Path.Combine(
            Path.GetDirectoryName(_tasksJsonPath)!,
            $"tasks_backup_{timestamp}.json"
        );
        File.Copy(_tasksJsonPath, backupPath);
    }
}
