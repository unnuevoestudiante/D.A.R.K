[CmdletBinding()]
param(
    [ValidateRange(10, 3600)]
    [int]$DurationSeconds = 180,
    [ValidateRange(100, 10000)]
    [int]$IntervalMs = 500,
    [string]$OutputPath,
    [string[]]$ProcessName = @("Jarvis", "electron", "python", "pythonw", "ollama")
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputPath = Join-Path $PSScriptRoot "dark-gpu-$stamp.csv"
}
if (Test-Path -LiteralPath $OutputPath) {
    throw "El archivo de salida ya existe; elige otra ruta: $OutputPath"
}

$counterPath = "\GPU Engine(*)\Utilization Percentage"
$deadline = [DateTime]::UtcNow.AddSeconds($DurationSeconds)
$previousCpu = @{}
$previousAt = [DateTime]::UtcNow
$pendingRows = [System.Collections.Generic.List[object]]::new()
$written = $false
$sampleIndex = 0

while ([DateTime]::UtcNow -lt $deadline) {
    $sampleAt = [DateTime]::UtcNow
    $elapsedMs = [Math]::Max(1, ($sampleAt - $previousAt).TotalMilliseconds)
    $gpuByPid = @{}

    try {
        $counter = Get-Counter -Counter $counterPath -ErrorAction Stop
    }
    catch {
        throw "No se pudo leer '$counterPath'. Comprueba que el contador GPU Engine esté disponible. $($_.Exception.Message)"
    }

    foreach ($reading in $counter.CounterSamples) {
        if ($reading.InstanceName -match "pid_(\d+)") {
            $pidValue = [int]$Matches[1]
            if (-not $gpuByPid.ContainsKey($pidValue)) {
                $gpuByPid[$pidValue] = [System.Collections.Generic.List[double]]::new()
            }
            $gpuByPid[$pidValue].Add([double]$reading.CookedValue)
        }
    }

    $allProcesses = @(Get-Process -ErrorAction SilentlyContinue)
    $processById = @{}
    foreach ($process in $allProcesses) {
        $processById[$process.Id] = $process
    }
    $selectedProcesses = @($allProcesses |
        Where-Object { $ProcessName -contains $_.ProcessName })
    $pids = @($gpuByPid.Keys) + @($selectedProcesses |
        ForEach-Object { $_.Id }) |
        Sort-Object -Unique

    foreach ($processId in $pids) {
        $process = $processById[[int]$processId]
        $name = if ($process) { $process.ProcessName } else { "pid_$processId" }
        $cpuSeconds = if ($process) { [double]$process.CPU } else { $null }
        $cpuPercent = $null
        if ($null -ne $cpuSeconds -and $previousCpu.ContainsKey($processId)) {
            $cpuPercent = [Math]::Round(
                (($cpuSeconds - $previousCpu[$processId]) * 100000 /
                    ($elapsedMs * [Environment]::ProcessorCount)),
                2)
        }
        if ($null -ne $cpuSeconds) {
            $previousCpu[$processId] = $cpuSeconds
        }

        $gpuValues = @()
        if ($gpuByPid.ContainsKey([int]$processId)) {
            $gpuValues = @($gpuByPid[[int]$processId].ToArray())
        }
        $gpuSum = if ($gpuValues.Count) {
            [Math]::Round(($gpuValues | Measure-Object -Sum).Sum, 2)
        } else { 0 }
        $gpuMax = if ($gpuValues.Count) {
            [Math]::Round(($gpuValues | Measure-Object -Maximum).Maximum, 2)
        } else { 0 }
        $memoryMb = if ($process) {
            [Math]::Round($process.WorkingSet64 / 1MB, 1)
        } else { $null }

        $pendingRows.Add([pscustomobject]@{
            timestamp_utc          = $sampleAt.ToString("o")
            wall_time_unix_ns      = [DateTimeOffset]::new($sampleAt).ToUnixTimeMilliseconds() * 1000000
            elapsed_ms             = [Math]::Round($elapsedMs, 1)
            process_id             = $processId
            process_name           = $name
            cpu_percent            = $cpuPercent
            working_set_mb         = $memoryMb
            gpu_engine_sum_percent = $gpuSum
            gpu_engine_max_percent = $gpuMax
            gpu_engine_count       = $gpuValues.Count
        })
    }

    $previousAt = $sampleAt
    $sampleIndex++
    if ($sampleIndex % 10 -eq 0) {
        $pendingRows | Export-Csv -LiteralPath $OutputPath -NoTypeInformation `
            -Append:$written -Encoding UTF8
        $pendingRows.Clear()
        $written = $true
    }

    $workMs = ([DateTime]::UtcNow - $sampleAt).TotalMilliseconds
    $sleepMs = [Math]::Max(0, $IntervalMs - $workMs)
    if ($sleepMs -gt 0) {
        Start-Sleep -Milliseconds ([int][Math]::Ceiling($sleepMs))
    }
}

if ($pendingRows.Count -gt 0) {
    $pendingRows | Export-Csv -LiteralPath $OutputPath -NoTypeInformation `
        -Append:$written -Encoding UTF8
}

Write-Output "Muestras guardadas en: $OutputPath"
