using DarkSetup.Downloads;
using DarkSetup.Manifest;
using DarkSetup.Provisioning;

namespace DarkSetup.Models;

public sealed record ModelProvisioningExecutionResult(
    ModelProvisioningPlan Plan,
    IReadOnlyList<ProvisioningStepResult> Steps);

public sealed class OllamaModelProvisioningService(
    OllamaModelInstaller modelInstaller,
    ProvisioningEngine provisioningEngine)
{
    public async Task<ModelProvisioningExecutionResult> RunAsync(
        IReadOnlyDictionary<string, string> selectedModelsByRole,
        VerifiedManifest manifest,
        string modelStorePath,
        string journalPath,
        IProgress<ModelPullProgress>? progress = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(selectedModelsByRole);
        ArgumentNullException.ThrowIfNull(manifest);
        ArgumentException.ThrowIfNullOrWhiteSpace(modelStorePath);
        ArgumentException.ThrowIfNullOrWhiteSpace(journalPath);

        var installedDigests = await modelInstaller.ReadInstalledDigestsAsync(cancellationToken);
        var availableBytes = GetAvailableBytes(modelStorePath);
        var plan = ModelProvisioningPlanner.Create(selectedModelsByRole, manifest, availableBytes, installedDigests);
        if (!plan.FitsExactStorage)
            throw new IOException($"Falta espacio libre en el almacén de Ollama: se necesitan {plan.RequiredDownloadBytes} bytes y hay {availableBytes}.");

        var orderedModels = plan.Models;
        var steps = new List<ProvisioningStep>(orderedModels.Count);
        string? previousStep = null;
        foreach (var selected in orderedModels)
        {
            var stepId = selected.Id;
            var dependencies = previousStep is null ? Array.Empty<string>() : [previousStep];
            steps.Add(new ProvisioningStep
            {
                Id = stepId,
                DependsOn = dependencies,
                ExecuteAsync = async token =>
                {
                    var freeBytes = GetAvailableBytes(modelStorePath);
                    await modelInstaller.InstallAsync(manifest, stepId, freeBytes, progress, token);
                },
                VerifyAsync = token => modelInstaller.IsInstalledAsync(manifest, stepId, token),
            });
            previousStep = stepId;
        }

        var results = await provisioningEngine.RunAsync(steps, journalPath, cancellationToken);
        return new ModelProvisioningExecutionResult(plan, results);
    }

    private static long GetAvailableBytes(string modelStorePath)
    {
        var fullPath = Path.GetFullPath(modelStorePath);
        var driveRoot = Path.GetPathRoot(fullPath);
        if (string.IsNullOrWhiteSpace(driveRoot))
            throw new IOException("No se pudo determinar el volumen del almacén de Ollama.");
        try { return new DriveInfo(driveRoot).AvailableFreeSpace; }
        catch (Exception error) when (error is ArgumentException or IOException or UnauthorizedAccessException)
        {
            throw new IOException("No se pudo consultar el espacio libre del almacén de Ollama.", error);
        }
    }
}
