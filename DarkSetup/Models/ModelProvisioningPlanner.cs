using DarkSetup.Manifest;

namespace DarkSetup.Models;

public sealed record ModelProvisioningPlan(
    IReadOnlyDictionary<string, string> SelectedModelsByRole,
    string ManifestPayloadSha256,
    long RequiredDownloadBytes,
    long? AvailableStorageBytes,
    bool FitsExactStorage,
    IReadOnlyList<ManifestModel> Models,
    IReadOnlyList<string> AlreadyInstalledModelIds,
    IReadOnlyList<string> MissingModelIds);

public static class ModelProvisioningPlanner
{
    public static ModelProvisioningPlan Create(IReadOnlyDictionary<string, string> selectedModelsByRole, VerifiedManifest manifest,
        long? availableStorageBytes = null,
        IReadOnlyDictionary<string, string>? installedModelDigests = null)
    {
        ArgumentNullException.ThrowIfNull(selectedModelsByRole);
        ArgumentNullException.ThrowIfNull(manifest);
        var allowedRoles = new HashSet<string>(["chat", "nucleus", "coder"], StringComparer.Ordinal);
        if (selectedModelsByRole.Count == 0 || selectedModelsByRole.Any(pair =>
                !allowedRoles.Contains(pair.Key) || string.IsNullOrWhiteSpace(pair.Value)))
            throw new InvalidDataException("Selecciona al menos un modelo por función válida (chat, nucleus o coder).");
        if (selectedModelsByRole.Values.Distinct(StringComparer.Ordinal).Count() != selectedModelsByRole.Count)
            throw new InvalidDataException("Un modelo no puede asignarse a más de una función.");

        var models = new List<ManifestModel>(selectedModelsByRole.Count);
        var alreadyInstalled = new List<string>(selectedModelsByRole.Count);
        var missing = new List<string>(selectedModelsByRole.Count);
        long requiredBytes = 0;
        foreach (var (role, modelId) in selectedModelsByRole)
        {
            var signed = manifest.Payload.Models.SingleOrDefault(model => model.Id == modelId)
                ?? throw new InvalidDataException($"El manifiesto firmado no contiene {modelId}.");
            if (signed.Backend != "ollama" || signed.Role != role || signed.MaximumDownloadBytes == 0
                || signed.Digest.Length != 71 || !signed.Digest.StartsWith("sha256:", StringComparison.Ordinal)
                || signed.Digest[7..].Any(character => !Uri.IsHexDigit(character)))
                throw new InvalidDataException($"El modelo firmado {modelId} no corresponde a la función {role}.");

            if (installedModelDigests is not null
                && installedModelDigests.TryGetValue(signed.ModelTag, out var localDigest))
            {
                if (!NormalizeDigest(localDigest).Equals(NormalizeDigest(signed.Digest), StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException($"{signed.ModelTag} ya existe con un digest distinto al firmado.");
                alreadyInstalled.Add(signed.Id);
            }
            else
            {
                requiredBytes = checked(requiredBytes + signed.MaximumDownloadBytes);
                missing.Add(signed.Id);
            }
            models.Add(signed);
        }

        return new ModelProvisioningPlan(new Dictionary<string, string>(selectedModelsByRole, StringComparer.Ordinal), manifest.PayloadSha256,
            requiredBytes, availableStorageBytes,
            requiredBytes == 0 || availableStorageBytes is { } available && available >= requiredBytes,
            models, alreadyInstalled, missing);
    }

    private static string NormalizeDigest(string digest) =>
        digest.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase) ? digest[7..] : digest;
}
