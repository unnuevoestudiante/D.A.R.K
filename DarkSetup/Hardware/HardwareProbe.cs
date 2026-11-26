using System.Runtime.InteropServices;
using System.Runtime.Versioning;

namespace DarkSetup.Hardware;

public sealed record CpuInfo(string? Name, int? PhysicalCores, int? LogicalProcessors);
public sealed record MemoryInfo(ulong? TotalBytes, ulong? AvailableBytes);
public sealed record GpuInfo(string Name, uint? VendorId, uint? DeviceId, ulong? DedicatedMemoryBytes, string? DriverVersion);
public sealed record OperatingSystemInfo(string? Name, string? Version, string? Build, string Architecture, bool IsWindows11OrNewer);
public sealed record StorageInfo(string TargetPath, string? DriveRoot, long? AvailableBytes);
public sealed record HardwareProbeResult(
    int SchemaVersion,
    DateTimeOffset ObservedAtUtc,
    OperatingSystemInfo OperatingSystem,
    CpuInfo Cpu,
    MemoryInfo Memory,
    IReadOnlyList<GpuInfo> Gpus,
    StorageInfo TargetStorage,
    string Profile,
    IReadOnlyList<string> Warnings);

public static class HardwareProbe
{
    private const ulong GiB = 1024UL * 1024 * 1024;

    public static HardwareProbeResult Collect(string? targetDirectory = null)
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("HardwareProbe requiere Windows.");

        var warnings = new List<string>();
        var target = Path.GetFullPath(string.IsNullOrWhiteSpace(targetDirectory)
            ? Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)
            : targetDirectory);
        var operatingSystem = ReadOperatingSystem();
        var cpu = ReadCpu(warnings);
        var memory = ReadMemory(warnings);
        var gpus = ReadGpus(warnings);
        var storage = ReadStorage(target, warnings);
        var maxVram = gpus.Where(gpu => gpu.DedicatedMemoryBytes.HasValue)
            .Select(gpu => gpu.DedicatedMemoryBytes!.Value).DefaultIfEmpty().Max();
        ulong? knownVram = gpus.Any(gpu => gpu.DedicatedMemoryBytes.HasValue) ? maxVram : null;

        return new HardwareProbeResult(1, DateTimeOffset.UtcNow, operatingSystem,
            cpu, memory, gpus, storage, Classify(memory.TotalBytes, knownVram), warnings);
    }

    public static string Classify(ulong? totalMemoryBytes, ulong? dedicatedVramBytes)
    {
        var ram = totalMemoryBytes ?? 0;
        var vram = dedicatedVramBytes ?? 0;
        if (ram >= 64 * GiB && vram >= 24 * GiB) return "station";
        if (ram >= 32 * GiB || vram >= 8 * GiB) return "high";
        if (ram >= 12 * GiB) return "standard";
        return "limited";
    }

    private static OperatingSystemInfo ReadOperatingSystem()
    {
        var version = Environment.OSVersion.Version;
        return new OperatingSystemInfo("Microsoft Windows", version.ToString(), version.Build.ToString(),
            RuntimeInformation.OSArchitecture.ToString(), version.Build >= 22000);
    }

    [SupportedOSPlatform("windows")]
    private static CpuInfo ReadCpu(List<string> warnings)
    {
        var processorCount = GetActiveProcessorCount(ushort.MaxValue);
        if (processorCount == 0) processorCount = (uint)Environment.ProcessorCount;
        var physicalCores = TryCountPhysicalCores();
        if (physicalCores is null) warnings.Add("No se pudo determinar el número de núcleos físicos.");
        var name = Environment.GetEnvironmentVariable("PROCESSOR_IDENTIFIER");
        if (string.IsNullOrWhiteSpace(name)) warnings.Add("El identificador de CPU no está disponible.");
        return new CpuInfo(string.IsNullOrWhiteSpace(name) ? null : name.Trim(), physicalCores,
            processorCount > 0 ? checked((int)processorCount) : null);
    }

    [SupportedOSPlatform("windows")]
    private static int? TryCountPhysicalCores()
    {
        uint bufferSize = 0;
        _ = GetLogicalProcessorInformationEx(0, IntPtr.Zero, ref bufferSize);
        if (Marshal.GetLastWin32Error() != 122 || bufferSize == 0) return null;
        var buffer = Marshal.AllocHGlobal(checked((int)bufferSize));
        try
        {
            if (!GetLogicalProcessorInformationEx(0, buffer, ref bufferSize)) return null;
            var count = 0;
            var offset = 0;
            while (offset + 8 <= bufferSize)
            {
                var relationship = Marshal.ReadInt32(buffer, offset);
                var size = Marshal.ReadInt32(buffer, offset + 4);
                if (size < 8 || offset + size > checked((int)bufferSize)) return null;
                if (relationship == 0) count++; // RelationProcessorCore
                offset += size;
            }
            return count > 0 ? count : null;
        }
        finally { Marshal.FreeHGlobal(buffer); }
    }

    [SupportedOSPlatform("windows")]
    private static MemoryInfo ReadMemory(List<string> warnings)
    {
        var status = new MemoryStatusEx { Length = (uint)Marshal.SizeOf<MemoryStatusEx>() };
        if (!GlobalMemoryStatusEx(ref status))
        {
            warnings.Add("Windows no devolvió la memoria física disponible.");
            return new MemoryInfo(null, null);
        }
        return new MemoryInfo(status.TotalPhysical, status.AvailablePhysical);
    }

    [SupportedOSPlatform("windows")]
    private static IReadOnlyList<GpuInfo> ReadGpus(List<string> warnings)
    {
        try
        {
            var adapters = EnumerateDxgiAdapters();
            if (adapters.Count == 0) warnings.Add("DXGI no detectó adaptadores gráficos físicos.");
            warnings.Add("La versión del controlador gráfico no se expone mediante DXGI y queda sin determinar.");
            return adapters.Select(adapter => new GpuInfo(adapter.Name, adapter.VendorId,
                adapter.DeviceId, adapter.DedicatedMemoryBytes, null)).ToArray();
        }
        catch (Exception error)
        {
            warnings.Add($"No se pudo consultar GPU/VRAM mediante DXGI: {error.GetType().Name}.");
            return [];
        }
    }

    private static StorageInfo ReadStorage(string target, List<string> warnings)
    {
        try
        {
            var root = Path.GetPathRoot(target);
            if (string.IsNullOrWhiteSpace(root)) throw new IOException("La ruta no tiene una unidad raíz.");
            var drive = new DriveInfo(root);
            if (!drive.IsReady) throw new IOException("La unidad no está disponible.");
            return new StorageInfo(target, root, drive.AvailableFreeSpace);
        }
        catch (Exception error)
        {
            warnings.Add($"No se pudo consultar el espacio de destino: {error.GetType().Name}.");
            return new StorageInfo(target, null, null);
        }
    }

    private static IReadOnlyList<DxgiAdapter> EnumerateDxgiAdapters()
    {
        var factoryId = new Guid("770aae78-f26f-4dba-a829-253c83d1b387");
        Marshal.ThrowExceptionForHR(CreateDXGIFactory1(ref factoryId, out var factory));
        try
        {
            var vtable = Marshal.ReadIntPtr(factory);
            var enumerate = Marshal.GetDelegateForFunctionPointer<EnumAdapters1Delegate>(
                Marshal.ReadIntPtr(vtable, 12 * IntPtr.Size));
            var adapters = new List<DxgiAdapter>();
            for (uint index = 0; ; index++)
            {
                var result = enumerate(factory, index, out var adapter);
                if (result == unchecked((int)0x887A0002)) break; // DXGI_ERROR_NOT_FOUND
                Marshal.ThrowExceptionForHR(result);
                try
                {
                    var adapterVtable = Marshal.ReadIntPtr(adapter);
                    var getDescription = Marshal.GetDelegateForFunctionPointer<GetDesc1Delegate>(
                        Marshal.ReadIntPtr(adapterVtable, 10 * IntPtr.Size));
                    Marshal.ThrowExceptionForHR(getDescription(adapter, out var description));
                    if ((description.Flags & 2) == 0 && !string.IsNullOrWhiteSpace(description.Description))
                        adapters.Add(new DxgiAdapter(description.Description.TrimEnd('\0'), description.VendorId,
                            description.DeviceId, description.DedicatedVideoMemory));
                }
                finally { Marshal.Release(adapter); }
            }
            return adapters;
        }
        finally { Marshal.Release(factory); }
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GlobalMemoryStatusEx(ref MemoryStatusEx status);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetLogicalProcessorInformationEx(int relationship, IntPtr buffer, ref uint returnedLength);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint GetActiveProcessorCount(ushort groupNumber);

    [DllImport("dxgi.dll", ExactSpelling = true)]
    private static extern int CreateDXGIFactory1(ref Guid interfaceId, out IntPtr factory);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    private struct MemoryStatusEx
    {
        public uint Length;
        public uint MemoryLoad;
        public ulong TotalPhysical;
        public ulong AvailablePhysical;
        public ulong TotalPageFile;
        public ulong AvailablePageFile;
        public ulong TotalVirtual;
        public ulong AvailableVirtual;
        public ulong AvailableExtendedVirtual;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct DxgiAdapterDesc1
    {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string Description;
        public uint VendorId;
        public uint DeviceId;
        public uint SubSysId;
        public uint Revision;
        public nuint DedicatedVideoMemory;
        public nuint DedicatedSystemMemory;
        public nuint SharedSystemMemory;
        public long AdapterLuid;
        public uint Flags;
    }

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate int EnumAdapters1Delegate(IntPtr factory, uint index, out IntPtr adapter);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate int GetDesc1Delegate(IntPtr adapter, out DxgiAdapterDesc1 description);

    private sealed record DxgiAdapter(string Name, uint VendorId, uint DeviceId, ulong DedicatedMemoryBytes);
}
