using System.Diagnostics;
using System.Security;
using Microsoft.Win32;

namespace DarkInstaller;

internal static class UninstallManager
{
    private const string RegistryPath = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\DARK";

    public static void Register(string installRoot, string displayVersion)
    {
        var executable = Environment.ProcessPath;
        if (string.IsNullOrWhiteSpace(executable) || !File.Exists(executable))
            throw new FileNotFoundException("No se pudo localizar el instalador para configurar la desinstalación.");

        var uninstallerDirectory = GetUninstallerDirectory();
        Directory.CreateDirectory(uninstallerDirectory);
        var uninstaller = Path.Combine(uninstallerDirectory, "DarkInstaller.exe");
        File.Copy(executable, uninstaller, overwrite: true);
        var manifestSource = Path.Combine(AppContext.BaseDirectory, "release-manifest.signed.json");
        var hostsSource = Path.Combine(AppContext.BaseDirectory, "release-source-hosts.txt");
        var hasRepairMetadata = File.Exists(manifestSource) && File.Exists(hostsSource);
        if (hasRepairMetadata)
        {
            File.Copy(manifestSource, Path.Combine(uninstallerDirectory, "release-manifest.signed.json"), overwrite: true);
            File.Copy(hostsSource, Path.Combine(uninstallerDirectory, "release-source-hosts.txt"), overwrite: true);
        }
        else
        {
            File.Delete(Path.Combine(uninstallerDirectory, "release-manifest.signed.json"));
            File.Delete(Path.Combine(uninstallerDirectory, "release-source-hosts.txt"));
        }

        using var entry = Registry.CurrentUser.CreateSubKey(RegistryPath, writable: true)
            ?? throw new IOException("No se pudo crear el registro de desinstalación por usuario.");
        entry.SetValue("DisplayName", "D.A.R.K.");
        entry.SetValue("DisplayVersion", displayVersion);
        entry.SetValue("InstallLocation", Path.GetFullPath(installRoot));
        entry.SetValue("DisplayIcon", Path.Combine(installRoot, "DarkSupervisor.exe"));
        entry.SetValue("UninstallString", $"\"{uninstaller}\" --uninstall");
        // No se anuncia todavía una acción de reparación en Windows: el manifiesto
        // integrado tiene vencimiento y aún no existe un canal autenticado de actualización.
        entry.SetValue("NoModify", 1, RegistryValueKind.DWord);
        entry.SetValue("NoRepair", 1, RegistryValueKind.DWord);
        entry.DeleteValue("ModifyPath", throwOnMissingValue: false);
        entry.SetValue("InstallDate", DateTime.Now.ToString("yyyyMMdd"));
    }

    public static string GetInstallLocation()
    {
        using var entry = Registry.CurrentUser.OpenSubKey(RegistryPath, writable: false)
            ?? throw new InvalidOperationException("No se encontró una instalación registrada de D.A.R.K.");
        var path = entry.GetValue("InstallLocation") as string;
        return string.IsNullOrWhiteSpace(path)
            ? throw new InvalidDataException("El registro no contiene una carpeta de instalación válida.")
            : Path.GetFullPath(path);
    }

    public static int Run()
    {
        try
        {
            using var entry = Registry.CurrentUser.OpenSubKey(RegistryPath, writable: false)
                ?? throw new InvalidOperationException("No se encontró el registro de instalación de D.A.R.K.");
            var rawPath = entry.GetValue("InstallLocation") as string;
            if (string.IsNullOrWhiteSpace(rawPath))
                throw new InvalidDataException("El registro de instalación no contiene una ruta válida.");

            var installRoot = Path.GetFullPath(rawPath);
            ValidateInstallRoot(installRoot);
            var previousInstallRoots = FindPreviousInstallBackups(installRoot);
            var message = "Se quitarán los archivos de la aplicación D.A.R.K. de esta carpeta:\n\n"
                + installRoot
                + (previousInstallRoots.Count == 0 ? "" : "\n\nTambién se quitarán estas copias de versiones anteriores:\n"
                    + string.Join("\n", previousInstallRoots))
                + "\n\nSe conservarán la configuración, las tareas, los modelos y los logs del usuario en %LOCALAPPDATA%\\DARK. "
                + "Los componentes opcionales instalados por separado, como Ollama, no se desinstalarán. "
                + "Después de confirmar, esta ventana se cerrará y empezará la limpieza.\n\n¿Continuar?";
            if (MessageBox.Show(message, "Desinstalar D.A.R.K.", MessageBoxButtons.YesNo,
                    MessageBoxIcon.Warning, MessageBoxDefaultButton.Button2) != DialogResult.Yes)
                return 0;

            EnsureInstalledAppIsStopped(installRoot);
            // Que no intente abrirse al encender el equipo una aplicación que ya no existe.
            InicioConWindows.Fijar(null, activo: false);
            foreach (var previousInstallRoot in previousInstallRoots) EnsureInstalledAppIsStopped(previousInstallRoot);
            foreach (var removalRoot in new[] { installRoot }.Concat(previousInstallRoots).Append(GetUninstallerDirectory()))
                EnsureNoReparsePointsBelow(removalRoot);
            // Primero se quita la aplicacion, aqui mismo y con resultado visible. El desinstalador y
            // la clave de "Aplicaciones instaladas" se conservan si algo falla, para poder reintentar
            // (antes se borraban a la vez y quedaba una entrada que apuntaba a un archivo inexistente).
            foreach (var folder in new[] { installRoot }.Concat(previousInstallRoots))
                RemoveFolderWithRetries(folder);
            ScheduleRemoval([], GetUninstallerDirectory());
            MessageBox.Show("D.A.R.K. se desinstaló.\n\nSe conservaron tu configuración, tareas, modelos y logs en %LOCALAPPDATA%\\DARK.",
                "Desinstalar D.A.R.K.", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return 0;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException
                                      or InvalidDataException or SecurityException or System.ComponentModel.Win32Exception)
        {
            MessageBox.Show("No se pudo desinstalar D.A.R.K.\n\n" + error.Message,
                "Desinstalación incompleta", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    private static IReadOnlyList<string> FindPreviousInstallBackups(string installRoot)
    {
        var parent = Path.GetDirectoryName(installRoot)
            ?? throw new InvalidDataException("No se pudo determinar la carpeta de instalación.");
        var prefix = Path.GetFileName(installRoot) + ".previous-";
        return Directory.EnumerateDirectories(parent, prefix + "*", SearchOption.TopDirectoryOnly)
            .Where(path => (File.GetAttributes(path) & FileAttributes.ReparsePoint) == 0
                && File.Exists(Path.Combine(path, "DarkSupervisor.exe"))
                && File.Exists(Path.Combine(path, "config", "runtime.json")))
            .Select(Path.GetFullPath)
            .ToArray();
    }

    private static void ValidateInstallRoot(string installRoot)
    {
        var root = Path.GetPathRoot(installRoot);
        var localAppData = Path.GetFullPath(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData));
        var protectedPaths = new[]
        {
            Path.Combine(localAppData, "DARK"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "Temp", "DARK"),
            Path.Combine(Path.GetTempPath(), "DARK"),
        }.Select(path => Path.GetFullPath(path));
        var uninstallerDirectory = Path.GetFullPath(GetUninstallerDirectory());
        if (string.IsNullOrWhiteSpace(root)
            || string.Equals(installRoot.TrimEnd(Path.DirectorySeparatorChar), root.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase)
            || protectedPaths.Any(path => PathsOverlap(installRoot, path))
            || IsSameOrChildPath(uninstallerDirectory, installRoot)
            || IsSameOrChildPath(installRoot, uninstallerDirectory))
            throw new InvalidDataException("La ruta registrada no es segura para desinstalar.");
        if (!Directory.Exists(installRoot)
            || (File.GetAttributes(installRoot) & FileAttributes.ReparsePoint) != 0
            || !File.Exists(Path.Combine(installRoot, "DarkSupervisor.exe"))
            || !File.Exists(Path.Combine(installRoot, "config", "runtime.json")))
            throw new InvalidDataException("La carpeta registrada no coincide con una instalación válida de D.A.R.K.");
    }

    private static bool IsSameOrChildPath(string candidate, string parent)
    {
        candidate = Path.GetFullPath(candidate).TrimEnd(Path.DirectorySeparatorChar);
        parent = Path.GetFullPath(parent).TrimEnd(Path.DirectorySeparatorChar);
        return string.Equals(candidate, parent, StringComparison.OrdinalIgnoreCase)
            || candidate.StartsWith(parent + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
    }

    private static bool PathsOverlap(string first, string second) => IsSameOrChildPath(first, second)
        || IsSameOrChildPath(second, first);

    private static void EnsureInstalledAppIsStopped(string installRoot) =>
        InstalledProcesses.EnsureStopped(installRoot, "desinstalarlo");

    private static void RemoveFolderWithRetries(string path)
    {
        Exception? last = null;
        for (var attempt = 0; attempt < 20; attempt++)
        {
            if (!Directory.Exists(path)) return;
            try
            {
                foreach (var file in Directory.EnumerateFiles(path, "*", SearchOption.AllDirectories))
                    File.SetAttributes(file, FileAttributes.Normal);
                Directory.Delete(path, recursive: true);
                return;
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
                last = error;
                Thread.Sleep(500);
            }
        }
        throw new IOException($"No se pudo quitar la carpeta {path}. Cierra cualquier programa que la esté usando "
            + $"(Explorador, terminal) y vuelve a desinstalar desde Aplicaciones instaladas. Detalle: {last?.Message}", last);
    }

    private static void EnsureNoReparsePointsBelow(string root)
    {
        if (!Directory.Exists(root)) return;
        var pending = new Stack<string>();
        pending.Push(root);
        while (pending.TryPop(out var current))
        {
            foreach (var path in Directory.EnumerateFileSystemEntries(current))
            {
                var attributes = File.GetAttributes(path);
                if ((attributes & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("Se encontró un enlace o punto de reanálisis dentro de la carpeta que se iba a quitar; no se borró nada.");
                if ((attributes & FileAttributes.Directory) != 0) pending.Push(path);
            }
        }
    }

    private static void ScheduleRemoval(IEnumerable<string> installRoots, string uninstallerDirectory)
    {
        var encodedPaths = installRoots.Append(uninstallerDirectory).Append(GetStartMenuShortcut())
            .Select(path => Convert.ToBase64String(System.Text.Encoding.Unicode.GetBytes(Path.GetFullPath(path))))
            .Select(value => "'" + value + "'");
        var script = "$paths = @(" + string.Join(",", encodedPaths) + "); $allRemoved = $true; "
            + "Start-Sleep -Seconds 2; "
            + "foreach ($encoded in $paths) { $path = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($encoded)); "
            + "for ($attempt = 0; $attempt -lt 20; $attempt++) { "
            + "if (-not (Test-Path -LiteralPath $path)) { break }; "
            + "try { Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop; break } "
            + "catch { Start-Sleep -Milliseconds 500 } }; "
            + "if (Test-Path -LiteralPath $path) { $allRemoved = $false } }; "
            + "if ($allRemoved) { Remove-Item -LiteralPath 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DARK' -Recurse -Force -ErrorAction SilentlyContinue }";
        var encodedScript = Convert.ToBase64String(System.Text.Encoding.Unicode.GetBytes(script));
        var process = Process.Start(new ProcessStartInfo("powershell.exe")
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
            ArgumentList = { "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encodedScript },
        });
        if (process is null) throw new IOException("No se pudo iniciar la limpieza final de la aplicación.");
        process.Dispose();
    }

    private static string GetUninstallerDirectory() => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "DARK", "setup", "uninstaller");

    private static string GetStartMenuShortcut() => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.StartMenu), "Programs", "D.A.R.K..lnk");
}
