using System.IO.Compression;

namespace DarkSetup.Downloads;

public static class ZipExtractor
{
    public static void ExtractSafely(string archivePath, string destinationRoot, long maximumExpandedBytes)
    {
        var destination = Path.GetFullPath(destinationRoot);
        var parent = Path.GetDirectoryName(destination) ?? throw new InvalidDataException("Destino ZIP inválido.");
        EnsureNoReparseAncestors(parent);
        Directory.CreateDirectory(parent);
        var temporary = destination + ".extracting-" + Guid.NewGuid().ToString("N");
        try
        {
            using var archive = ZipFile.OpenRead(archivePath);
            if (archive.Entries.Count > 100_000) throw new InvalidDataException("El ZIP supera el límite de archivos admitido.");
            Directory.CreateDirectory(temporary);
            long copied = 0;
            foreach (var entry in archive.Entries)
            {
                var normalized = entry.FullName.Replace('\\', '/');
                if (normalized.StartsWith('/') || normalized.Contains(':')
                    || normalized.Split('/').Any(segment => segment is ".." or "."))
                    throw new InvalidDataException("El ZIP contiene una ruta absoluta o fuera del destino permitido.");
                if (((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000)
                    throw new InvalidDataException("El ZIP contiene un enlace simbólico no admitido.");
                var relative = normalized.TrimEnd('/');
                if (relative.Length == 0) continue;
                var outputPath = Path.GetFullPath(Path.Combine(temporary, relative.Replace('/', Path.DirectorySeparatorChar)));
                if (!outputPath.StartsWith(temporary + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("La ruta ZIP sale del destino permitido.");
                if (normalized.EndsWith('/')) { Directory.CreateDirectory(outputPath); continue; }
                Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
                using var input = entry.Open();
                using var output = new FileStream(outputPath, FileMode.CreateNew, FileAccess.Write, FileShare.None);
                CopyBounded(input, output, maximumExpandedBytes, ref copied);
            }
            if (Directory.Exists(destination) || File.Exists(destination))
                throw new IOException("La carpeta de extracción ya existe.");
            Directory.Move(temporary, destination);
        }
        catch
        {
            if (Directory.Exists(temporary)) Directory.Delete(temporary, recursive: true);
            throw;
        }
    }

    public static void CopyBounded(Stream input, Stream output, long maximumBytes, ref long copiedBytes)
    {
        var buffer = new byte[81920];
        int read;
        while ((read = input.Read(buffer, 0, buffer.Length)) > 0)
        {
            copiedBytes = checked(copiedBytes + read);
            if (copiedBytes > maximumBytes)
                throw new InvalidDataException("El contenido real del ZIP supera el tamaño estimado del manifiesto.");
            output.Write(buffer, 0, read);
        }
    }

    private static void EnsureNoReparseAncestors(string path)
    {
        var current = Path.GetFullPath(path);
        while (!string.IsNullOrEmpty(current))
        {
            if (Directory.Exists(current) && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("La ruta de extracción atraviesa un punto de reanálisis.");
            var next = Path.GetDirectoryName(current);
            if (next == current) break;
            current = next ?? "";
        }
    }
}
