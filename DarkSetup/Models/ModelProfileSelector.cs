using System.Text.Json;
using DarkSetup.Hardware;

namespace DarkSetup.Models;

public sealed record ProfileModel(string Role, string ManifestModelId, string ModelTag, string Digest,
    long EstimatedRamMB, int Priority, long EstimatedDownloadMB, string SourceUri, string LicenseId, string LicenseUri);

public sealed record ModelProfileSelection(string HardwareProfile, string SelectedProfile,
    long ManagerMemoryBudgetMB, bool FitsMemoryBudget, long? AvailableStorageMB,
    long? AvailableStorageBytes, long EstimatedProfileStorageMB, bool FitsStorage, IReadOnlyList<ProfileModel> Models);

public static class ModelProfileSelector
{
    private const long MiB = 1024 * 1024;
    private static readonly string[] Roles = ["chat", "nucleus", "coder"];
    private static readonly string[] ProfileOrder = ["limited", "standard", "high", "station"];

    public static ModelProfileSelection Select(HardwareProbeResult hardware,
        string profileCatalogPath, string managerModelsPath, double? memoryBudgetRatioOverride = null)
    {
        ArgumentNullException.ThrowIfNull(hardware);
        using var catalog = JsonDocument.Parse(File.ReadAllBytes(profileCatalogPath));
        using var managerModels = JsonDocument.Parse(File.ReadAllBytes(managerModelsPath));
        var root = catalog.RootElement;
        if (!root.TryGetProperty("schemaVersion", out var version) || version.GetInt32() != 1
            || !root.TryGetProperty("profiles", out var profiles) || profiles.ValueKind != JsonValueKind.Object)
            throw new InvalidDataException("El catálogo de perfiles de modelos no tiene un formato admitido.");

        var memoryBudgetRatio = memoryBudgetRatioOverride
            ?? (root.TryGetProperty("memoryBudgetRatio", out var configuredRatio) ? configuredRatio.GetDouble() : double.NaN);
        if (memoryBudgetRatio is <= 0 or > 1 || double.IsNaN(memoryBudgetRatio))
            throw new InvalidDataException("El catálogo debe declarar memoryBudgetRatio entre 0 y 1.");

        var memoryBudget = hardware.Memory.TotalBytes is { } totalBytes
            ? (long)((totalBytes / (double)MiB) * memoryBudgetRatio)
            : 0;
        var requested = ProfileOrder.Contains(hardware.Profile, StringComparer.Ordinal)
            ? hardware.Profile
            : "limited";
        var requestedIndex = Array.IndexOf(ProfileOrder, requested);

        for (var index = requestedIndex; index >= 0; index--)
        {
            var profileName = ProfileOrder[index];
            if (!profiles.TryGetProperty(profileName, out var profile))
                throw new InvalidDataException($"El catálogo no contiene el perfil {profileName}.");
            var models = ReadProfile(profileName, profile, managerModels.RootElement);
            var maximumSingleModel = models.Max(model => model.EstimatedRamMB);
            if (maximumSingleModel <= memoryBudget || profileName == "limited")
            {
                var storageEstimate = models.Sum(model => model.EstimatedDownloadMB);
                var availableStorage = hardware.TargetStorage.AvailableBytes is { } available
                    ? available / MiB
                    : (long?)null;
                var availableStorageBytes = hardware.TargetStorage.AvailableBytes;
                return new ModelProfileSelection(hardware.Profile, profileName, memoryBudget,
                    maximumSingleModel <= memoryBudget, availableStorage, availableStorageBytes, storageEstimate,
                    availableStorage is { } space && space >= storageEstimate, models);
            }
        }

        throw new InvalidDataException("No se pudo resolver un perfil de modelos.");
    }

    private static IReadOnlyList<ProfileModel> ReadProfile(string profileName, JsonElement profile,
        JsonElement managerRegistry)
    {
        if (profile.ValueKind != JsonValueKind.Object
            || !profile.EnumerateObject().Select(property => property.Name).ToHashSet(StringComparer.Ordinal)
                .SetEquals(Roles))
            throw new InvalidDataException($"El perfil {profileName} debe declarar chat, nucleus y coder.");

        var result = new List<ProfileModel>(Roles.Length);
        foreach (var role in Roles)
        {
            var entry = profile.GetProperty(role);
            var modelTag = ReadString(entry, profileName == "standard" ? "managerModel" : "modelTag");
            long ramMb;
            int priority;
            if (!entry.TryGetProperty("estimatedDownloadMB", out var download)
                || !download.TryGetInt64(out var downloadMb) || downloadMb <= 0)
                throw new InvalidDataException($"El modelo {modelTag} no tiene una estimación de descarga válida.");
            if (profileName == "standard")
            {
                if (!managerRegistry.TryGetProperty(modelTag, out var managerModel))
                    throw new InvalidDataException($"El modelo estándar {modelTag} no existe en DarkManager/models.json.");
                if (!managerModel.TryGetProperty("ramEstimadaMB", out var ram)
                    || !ram.TryGetInt64(out ramMb)
                    || !managerModel.TryGetProperty("prioridad", out var order)
                    || !order.TryGetInt32(out priority))
                    throw new InvalidDataException($"El registro estándar {modelTag} no tiene memoria o prioridad válidas.");
            }
            else
            {
                if (!entry.TryGetProperty("estimatedRamMB", out var ram)
                    || !ram.TryGetInt64(out ramMb)
                    || !entry.TryGetProperty("priority", out var order)
                    || !order.TryGetInt32(out priority))
                    throw new InvalidDataException($"El modelo {modelTag} no tiene memoria o prioridad válidas.");
            }
            if (ramMb <= 0 || priority < 1)
                throw new InvalidDataException($"Valores de memoria/prioridad inválidos para {modelTag}.");

            var sourceUri = ReadString(entry, "sourceUri");
            var digest = ReadString(entry, "digest");
            if (digest.Length != 71 || !digest.StartsWith("sha256:", StringComparison.Ordinal)
                || digest[7..].Any(character => !Uri.IsHexDigit(character)))
                throw new InvalidDataException($"El digest de {modelTag} debe ser SHA-256 completo.");
            var licenseId = ReadString(entry, "licenseId");
            var licenseUri = ReadString(entry, "licenseUri");
            if (!Uri.TryCreate(sourceUri, UriKind.Absolute, out var source) || source.Scheme != Uri.UriSchemeHttps
                || !Uri.TryCreate(licenseUri, UriKind.Absolute, out var license) || license.Scheme != Uri.UriSchemeHttps)
                throw new InvalidDataException($"El origen o la licencia de {modelTag} debe usar HTTPS.");
            result.Add(new ProfileModel(role, $"{profileName}-{role}", modelTag, digest, ramMb,
                priority, downloadMb, sourceUri, licenseId, licenseUri));
        }
        return result;
    }

    private static string ReadString(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(value.GetString()))
            throw new InvalidDataException($"Falta el campo {name} en el perfil de modelos.");
        return value.GetString()!;
    }
}
