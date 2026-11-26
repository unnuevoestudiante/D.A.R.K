using System.Text.Json;
using System.Text.Json.Serialization;

namespace DarkSetup.Provisioning;

public enum ProvisioningStepStatus
{
    Pending,
    Running,
    Succeeded,
    Failed,
    Blocked,
    Interrupted,
}

public sealed record ProvisioningStepResult(
    string Id,
    ProvisioningStepStatus Status,
    string? FailureCode = null,
    string? FailureMessage = null,
    DateTimeOffset? UpdatedAtUtc = null);

public sealed class ProvisioningStep
{
    public required string Id { get; init; }
    public IReadOnlyList<string> DependsOn { get; init; } = [];
    public required Func<CancellationToken, Task> ExecuteAsync { get; init; }
    public required Func<CancellationToken, Task<bool>> VerifyAsync { get; init; }
    public Func<CancellationToken, Task>? RecoverAsync { get; init; }
}

public sealed class ProvisioningException(string code, string safeMessage) : Exception(safeMessage)
{
    public string Code { get; } = code;
}

public sealed class ProvisioningEngine
{
    private const int SchemaVersion = 1;
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter() },
    };
    private readonly SemaphoreSlim _gate = new(1, 1);

    public async Task<IReadOnlyList<ProvisioningStepResult>> RunAsync(
        IEnumerable<ProvisioningStep> requestedSteps,
        string journalPath,
        CancellationToken cancellationToken = default)
    {
        var steps = OrderAndValidate(requestedSteps);
        var fullPath = Path.GetFullPath(journalPath);
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var journal = await LoadJournalAsync(fullPath, steps, cancellationToken);
            foreach (var step in steps)
            {
                cancellationToken.ThrowIfCancellationRequested();
                var current = journal.Steps[step.Id];

                if (step.DependsOn.Any(dependency => journal.Steps[dependency].Status != ProvisioningStepStatus.Succeeded))
                {
                    journal.Steps[step.Id] = current with
                    {
                        Status = ProvisioningStepStatus.Blocked,
                        FailureCode = "dependency_incomplete",
                        FailureMessage = "Una dependencia obligatoria no terminó correctamente.",
                        UpdatedAtUtc = DateTimeOffset.UtcNow,
                    };
                    await SaveJournalAsync(fullPath, journal);
                    continue;
                }

                var wasInterrupted = current.Status is ProvisioningStepStatus.Running or ProvisioningStepStatus.Interrupted;
                if (wasInterrupted)
                {
                    journal.Steps[step.Id] = current with
                    {
                        Status = ProvisioningStepStatus.Interrupted,
                        FailureCode = "previous_run_interrupted",
                        FailureMessage = "La ejecución anterior se interrumpió; se comprobará el estado antes de reanudar.",
                        UpdatedAtUtc = DateTimeOffset.UtcNow,
                    };
                    await SaveJournalAsync(fullPath, journal);
                    if (step.RecoverAsync is not null)
                    {
                        try
                        {
                            await step.RecoverAsync(cancellationToken);
                            if (await step.VerifyAsync(cancellationToken))
                            {
                                await MarkSucceededAsync(fullPath, journal, step.Id);
                                continue;
                            }
                        }
                        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
                        {
                            throw;
                        }
                        catch (Exception error)
                        {
                            journal.Steps[step.Id] = new ProvisioningStepResult(
                                step.Id, ProvisioningStepStatus.Failed, "recovery_failed",
                                error is ProvisioningException safe ? safe.Message : "No se pudo recuperar la operación anterior.",
                                DateTimeOffset.UtcNow);
                            await SaveJournalAsync(fullPath, journal);
                            continue;
                        }
                    }
                }

                bool alreadyVerified;
                try { alreadyVerified = await step.VerifyAsync(cancellationToken); }
                catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
                catch (Exception error)
                {
                    journal.Steps[step.Id] = new ProvisioningStepResult(
                        step.Id, ProvisioningStepStatus.Failed, "verification_failed",
                        error is ProvisioningException safe ? safe.Message : "No se pudo comprobar el estado del componente.",
                        DateTimeOffset.UtcNow);
                    await SaveJournalAsync(fullPath, journal);
                    continue;
                }
                if (alreadyVerified)
                {
                    await MarkSucceededAsync(fullPath, journal, step.Id);
                    continue;
                }

                journal.Steps[step.Id] = new ProvisioningStepResult(
                    step.Id, ProvisioningStepStatus.Running,
                    UpdatedAtUtc: DateTimeOffset.UtcNow);
                await SaveJournalAsync(fullPath, journal);
                try
                {
                    await step.ExecuteAsync(cancellationToken);
                    if (!await step.VerifyAsync(cancellationToken))
                        throw new ProvisioningException("verification_failed", "La verificación posterior no confirmó el componente.");
                    await MarkSucceededAsync(fullPath, journal, step.Id);
                }
                catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
                {
                    journal.Steps[step.Id] = new ProvisioningStepResult(
                        step.Id, ProvisioningStepStatus.Interrupted,
                        "cancelled", "La operación se interrumpió y puede reanudarse.", DateTimeOffset.UtcNow);
                    await SaveJournalAsync(fullPath, journal);
                    throw;
                }
                catch (Exception error)
                {
                    journal.Steps[step.Id] = new ProvisioningStepResult(
                        step.Id, ProvisioningStepStatus.Failed,
                        error is ProvisioningException provisioning ? provisioning.Code : "operation_failed",
                        error is ProvisioningException safe ? safe.Message : "La operación falló; el estado se guardó para reparación.",
                        DateTimeOffset.UtcNow);
                    await SaveJournalAsync(fullPath, journal);
                }
            }

            return steps.Select(step => journal.Steps[step.Id]).ToArray();
        }
        finally { _gate.Release(); }
    }

    private static async Task MarkSucceededAsync(string path, ProvisioningJournal journal, string id)
    {
        journal.Steps[id] = new ProvisioningStepResult(
            id, ProvisioningStepStatus.Succeeded, UpdatedAtUtc: DateTimeOffset.UtcNow);
        await SaveJournalAsync(path, journal);
    }

    private static List<ProvisioningStep> OrderAndValidate(IEnumerable<ProvisioningStep> requested)
    {
        var steps = requested.ToDictionary(step => step.Id, StringComparer.Ordinal);
        if (steps.Count == 0) throw new ArgumentException("El grafo de aprovisionamiento está vacío.", nameof(requested));
        foreach (var step in steps.Values)
        {
            if (string.IsNullOrWhiteSpace(step.Id) || step.Id.Length > 128)
                throw new ArgumentException("Cada paso requiere un identificador de 1 a 128 caracteres.", nameof(requested));
            if (step.ExecuteAsync is null || step.VerifyAsync is null)
                throw new ArgumentException($"El paso {step.Id} requiere acción y verificación.", nameof(requested));
            if (step.DependsOn.Distinct(StringComparer.Ordinal).Count() != step.DependsOn.Count)
                throw new ArgumentException($"El paso {step.Id} repite dependencias.", nameof(requested));
            foreach (var dependency in step.DependsOn)
                if (!steps.ContainsKey(dependency))
                    throw new ArgumentException($"El paso {step.Id} depende del paso inexistente {dependency}.", nameof(requested));
        }

        var ordered = new List<ProvisioningStep>();
        var visited = new HashSet<string>(StringComparer.Ordinal);
        var active = new HashSet<string>(StringComparer.Ordinal);
        void Visit(ProvisioningStep step)
        {
            if (visited.Contains(step.Id)) return;
            if (!active.Add(step.Id)) throw new ArgumentException("El grafo de aprovisionamiento contiene un ciclo.", nameof(requested));
            foreach (var dependency in step.DependsOn.OrderBy(id => id, StringComparer.Ordinal)) Visit(steps[dependency]);
            active.Remove(step.Id);
            visited.Add(step.Id);
            ordered.Add(step);
        }
        foreach (var step in steps.Values.OrderBy(step => step.Id, StringComparer.Ordinal)) Visit(step);
        return ordered;
    }

    private static async Task<ProvisioningJournal> LoadJournalAsync(
        string path, IReadOnlyList<ProvisioningStep> steps, CancellationToken cancellationToken)
    {
        if (!File.Exists(path))
        {
            var initial = new ProvisioningJournal(
                SchemaVersion, Guid.NewGuid().ToString("N"), DateTimeOffset.UtcNow,
                steps.ToDictionary(step => step.Id,
                    step => new ProvisioningStepResult(step.Id, ProvisioningStepStatus.Pending,
                        UpdatedAtUtc: DateTimeOffset.UtcNow), StringComparer.Ordinal));
            await SaveJournalAsync(path, initial);
            return initial;
        }

        var journalBytes = await File.ReadAllBytesAsync(path, cancellationToken);
        var journal = JsonSerializer.Deserialize<ProvisioningJournal>(journalBytes, JsonOptions)
            ?? throw new InvalidDataException("El journal de aprovisionamiento está vacío o inválido.");
        if (journal.SchemaVersion != SchemaVersion)
            throw new InvalidDataException($"Versión de journal no compatible: {journal.SchemaVersion}.");
        if (journal.Steps.Values.Any(record => !Enum.IsDefined(record.Status)))
            throw new InvalidDataException("El journal contiene estados desconocidos.");
        foreach (var step in steps)
            if (!journal.Steps.ContainsKey(step.Id))
                journal.Steps[step.Id] = new ProvisioningStepResult(step.Id, ProvisioningStepStatus.Pending,
                    UpdatedAtUtc: DateTimeOffset.UtcNow);
        foreach (var retired in journal.Steps.Keys.Except(steps.Select(step => step.Id), StringComparer.Ordinal).ToArray())
            journal.Steps.Remove(retired);
        await SaveJournalAsync(path, journal);
        return journal;
    }

    private static async Task SaveJournalAsync(string path, ProvisioningJournal journal)
    {
        var directory = Path.GetDirectoryName(path);
        if (string.IsNullOrWhiteSpace(directory)) throw new InvalidOperationException("El journal debe tener una carpeta destino.");
        Directory.CreateDirectory(directory);
        journal = journal with { UpdatedAtUtc = DateTimeOffset.UtcNow };
        var temporary = path + ".tmp";
        await using (var stream = new FileStream(temporary, FileMode.Create, FileAccess.Write, FileShare.None,
            16 * 1024, FileOptions.Asynchronous | FileOptions.WriteThrough))
        {
            await JsonSerializer.SerializeAsync(stream, journal, JsonOptions);
            await stream.FlushAsync();
        }
        File.Move(temporary, path, overwrite: true);
    }

    private sealed record ProvisioningJournal(
        int SchemaVersion,
        string RunId,
        DateTimeOffset UpdatedAtUtc,
        Dictionary<string, ProvisioningStepResult> Steps);
}
