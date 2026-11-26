namespace DarkSetup;

public sealed class RetryableCancellation : IDisposable
{
    private CancellationTokenSource? _source;
    public CancellationToken BeginRun()
    {
        _source?.Dispose();
        _source = new CancellationTokenSource();
        return _source.Token;
    }
    public void Cancel() => _source?.Cancel();
    public void EndRun() { _source?.Dispose(); _source = null; }
    public void Dispose() => EndRun();
}
