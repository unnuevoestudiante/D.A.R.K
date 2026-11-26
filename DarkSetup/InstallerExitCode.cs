namespace DarkSetup;

public static class InstallerExitCode
{
    public static bool IsAccepted(int exitCode) => exitCode is 0 or 3010;
    public static bool RequiresRestart(int exitCode) => exitCode == 3010;
}
