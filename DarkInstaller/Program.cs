using System.Reflection;

namespace DarkInstaller;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        if (args.Length == 1 && string.Equals(args[0], "--uninstall", StringComparison.OrdinalIgnoreCase))
        {
            Environment.ExitCode = UninstallManager.Run();
            return;
        }
        string? repairPath = null;
        if (args.Length == 1 && string.Equals(args[0], "--repair", StringComparison.OrdinalIgnoreCase))
        {
            try { repairPath = UninstallManager.GetInstallLocation(); }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException
                                          or System.Security.SecurityException)
            {
                MessageBox.Show("No se pudo determinar dónde está instalado D.A.R.K.\n\n" + error.Message,
                    "No se pudo preparar la reparación", MessageBoxButtons.OK, MessageBoxIcon.Error);
                Environment.ExitCode = 1;
                return;
            }
        }
        if (args.Length >= 2 && string.Equals(args[0], "--snapshot", StringComparison.OrdinalIgnoreCase)
            && string.Equals(ReadMetadata("InstallerDistributionChannel"), "Development", StringComparison.OrdinalIgnoreCase))
        {
            // Herramienta de desarrollo: abre la ventana, la captura como PNG y sale.
            // args: --snapshot <png> [ancho alto]
            var form = new InstallerForm(repairPath);
            if (args.Length >= 4 && int.TryParse(args[2], out var w) && int.TryParse(args[3], out var h))
                form.ClientSize = new Size(w, h);
            SnapshotTool.Run(form, args[1]);
            return;
        }
        Application.Run(new InstallerForm(repairPath));
    }

    private static string? ReadMetadata(string key) => typeof(Program).Assembly
        .GetCustomAttributes<AssemblyMetadataAttribute>()
        .SingleOrDefault(attribute => attribute.Key == key)?.Value;
}

internal static class SnapshotTool
{
    public static void Run(Form form, string path)
    {
        var timer = new System.Windows.Forms.Timer { Interval = 1500 };
        timer.Tick += (_, _) =>
        {
            timer.Stop();
            var bounds = form.Bounds;
            using var bitmap = new Bitmap(bounds.Width, bounds.Height);
            using (var graphics = Graphics.FromImage(bitmap))
                graphics.CopyFromScreen(bounds.Location, Point.Empty, bounds.Size);
            bitmap.Save(path, System.Drawing.Imaging.ImageFormat.Png);
            var lines = new List<string>();
            void Dump(Control c, int depth)
            {
                lines.Add(new string(' ', depth * 2) + c.GetType().Name + " '" + (c.Text.Length > 25 ? c.Text[..25] : c.Text).Replace(Environment.NewLine, " ") + "' " + c.Bounds + (c.Visible ? "" : " HIDDEN") + " dock=" + c.Dock);
                foreach (Control child in c.Controls) Dump(child, depth + 1);
            }
            Dump(form, 0);
            File.WriteAllLines(path + ".txt", lines);
            form.Close();
        };
        form.Shown += (_, _) => { form.Activate(); timer.Start(); };
        Application.Run(form);
    }
}
