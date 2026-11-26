using Microsoft.Win32;

namespace DarkInstaller;

/// <summary>
/// «Abrir D.A.R.K. al encender el equipo»: una entrada en HKCU\...\Run, solo para este usuario y sin permisos de
/// administrador. La misma clave la lee y la cambia el Centro de configuración (Sistema); el desinstalador la quita.
/// </summary>
internal static class InicioConWindows
{
    internal const string ClaveRun = @"Software\Microsoft\Windows\CurrentVersion\Run";
    internal const string NombreValor = "D.A.R.K.";

    /// <summary>Activa (con la ruta del Supervisor) o quita el inicio automático.</summary>
    public static void Fijar(string? supervisor, bool activo)
    {
        using var clave = Registry.CurrentUser.CreateSubKey(ClaveRun, writable: true)
            ?? throw new InvalidOperationException("No se pudo abrir la lista de programas de inicio de Windows.");
        if (activo && supervisor is not null)
            clave.SetValue(NombreValor, $"\"{supervisor}\"", RegistryValueKind.String);
        else if (clave.GetValue(NombreValor) is not null)
            clave.DeleteValue(NombreValor, throwOnMissingValue: false);
    }

    public static bool Activo()
    {
        using var clave = Registry.CurrentUser.OpenSubKey(ClaveRun, writable: false);
        return clave?.GetValue(NombreValor) is string;
    }
}
