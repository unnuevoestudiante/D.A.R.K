using System.ComponentModel;
using System.Diagnostics;

namespace DarkInstaller;

/// <summary>
/// Procesos que corren desde la carpeta instalada de D.A.R.K.
/// Una sesion activa (Supervisor o Electron) se respeta: se pide cerrarla. Los restos huerfanos
/// (Manager, Node, Python que quedaron vivos tras un cierre abrupto) se terminan, porque si no
/// bloquean los archivos y dejan la actualizacion o desinstalacion a medias.
/// </summary>
internal static class InstalledProcesses
{
    private static readonly string[] SessionProcessNames = ["darksupervisor", "electron"];

    public static void EnsureStopped(string installRoot, string actionDescription)
    {
        var prefix = Path.EndsInDirectorySeparator(installRoot) ? installRoot : installRoot + Path.DirectorySeparatorChar;
        var running = FindUnder(prefix);
        try
        {
            if (running.Any(item => SessionProcessNames.Contains(item.Name, StringComparer.OrdinalIgnoreCase)))
                throw new IOException($"Cierra D.A.R.K. antes de {actionDescription}.");

            foreach (var item in running)
            {
                try
                {
                    item.Process.Kill(entireProcessTree: true);
                    if (!item.Process.WaitForExit(8000))
                        throw new IOException($"No se pudo cerrar {item.Name} (PID {item.Process.Id}), que quedó abierto desde la carpeta de D.A.R.K.");
                }
                catch (InvalidOperationException)
                {
                    // El proceso ya terminó.
                }
                catch (Win32Exception error)
                {
                    throw new IOException($"No se pudo cerrar {item.Name} (PID {item.Process.Id}): {error.Message}", error);
                }
            }
        }
        finally
        {
            foreach (var item in running) item.Process.Dispose();
        }
    }

    private static List<(Process Process, string Name)> FindUnder(string prefix)
    {
        var found = new List<(Process, string)>();
        foreach (var process in Process.GetProcesses())
        {
            var keep = false;
            try
            {
                var executable = process.MainModule?.FileName;
                if (executable is not null
                    && Path.GetFullPath(executable).StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                {
                    found.Add((process, process.ProcessName));
                    keep = true;
                }
            }
            catch (Exception error) when (error is Win32Exception or InvalidOperationException or NotSupportedException)
            {
                // Proceso del sistema, de otra sesion o ya terminado: no es de esta instalacion.
            }
            finally
            {
                if (!keep) process.Dispose();
            }
        }
        return found;
    }
}
