<#
.SYNOPSIS
  Quita una instalacion de D.A.R.K. que quedo bloqueada, SOLO en el perfil donde se ejecuta, y
  si algo impide borrarla, dice exactamente que archivo y por que.

.PARAMETER TambienDatos
  Ademas borra %LOCALAPPDATA%\DARK (configuracion, datos, logs, descargas). Por defecto se conservan.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File C:\Users\Public\DarkScripts\limpiar_dark_perfil.ps1
#>
param([switch]$TambienDatos)

$programa = Join-Path $env:LOCALAPPDATA "Programs\DARK"
$datos    = Join-Path $env:LOCALAPPDATA "DARK"
$acceso   = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\D.A.R.K..lnk"
$clave    = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\DARK"
$resultados = "C:\Users\Public\DarkResultados"
New-Item -ItemType Directory -Force $resultados | Out-Null
$registro = Join-Path $resultados ("limpieza-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt")
Start-Transcript -Path $registro | Out-Null
Write-Host "Perfil: $env:USERNAME   Carpeta de la aplicacion: $programa" -ForegroundColor Cyan

function Prefijo($ruta) { if ($ruta.EndsWith("\")) { $ruta } else { $ruta + "\" } }
$prefijos = @((Prefijo $programa), (Prefijo (Join-Path $datos "setup\uninstaller")))

# --- 1. Procesos: por ejecutable, por modulos cargados y por linea de comandos ---------------
Write-Host "`n[1] Buscando quien usa la carpeta..." -ForegroundColor Cyan
$hallados = @{}
foreach ($proc in Get-Process -ErrorAction SilentlyContinue) {
    $motivo = $null
    try { if ($proc.Path -and ($prefijos | Where-Object { $proc.Path.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) })) { $motivo = "ejecutable dentro de la carpeta" } } catch {}
    if (-not $motivo) {
        try { foreach ($m in $proc.Modules) { if ($prefijos | Where-Object { $m.FileName.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) }) { $motivo = "modulo cargado: $($m.FileName)"; break } } } catch {}
    }
    if ($motivo) { $hallados[$proc.Id] = [pscustomobject]@{ Nombre = $proc.ProcessName; Id = $proc.Id; Motivo = $motivo } }
}
foreach ($c in Get-CimInstance Win32_Process -ErrorAction SilentlyContinue) {
    if ($c.CommandLine -and ($prefijos | Where-Object { $c.CommandLine.IndexOf($_, [StringComparison]::OrdinalIgnoreCase) -ge 0 }) -and $c.ProcessId -ne $PID -and -not $hallados.ContainsKey([int]$c.ProcessId)) {
        $hallados[[int]$c.ProcessId] = [pscustomobject]@{ Nombre = $c.Name; Id = [int]$c.ProcessId; Motivo = "linea de comandos menciona la carpeta" }
    }
}
if ($hallados.Count -gt 0) {
    $hallados.Values | Format-Table Nombre, Id, Motivo -AutoSize -Wrap
    foreach ($h in $hallados.Values) {
        if ($h.Id -eq $PID) { continue }
        try { Stop-Process -Id $h.Id -Force -ErrorAction Stop; Write-Host "terminado $($h.Nombre) $($h.Id)" } catch { Write-Host "NO se pudo terminar $($h.Nombre) $($h.Id): $($_.Exception.Message)" -ForegroundColor Red }
    }
    Start-Sleep -Seconds 2
} else { Write-Host "Ningun proceso visible usa la carpeta." -ForegroundColor Green }

# --- 2. Borrado con diagnostico ------------------------------------------------------------
function Intentar-Borrar($ruta) {
    # a) .NET: el mensaje de error nombra el archivo exacto que falla
    try { [System.IO.Directory]::Delete($ruta, $true); return $true } catch { Write-Host "  .NET Directory.Delete: $($_.Exception.Message)" -ForegroundColor Yellow }
    # b) archivo por archivo: lista los que fallan y por que
    $fallos = @()
    Get-ChildItem -LiteralPath $ruta -Recurse -Force -File -ErrorAction SilentlyContinue | ForEach-Object {
        try { [System.IO.File]::SetAttributes($_.FullName, 'Normal'); [System.IO.File]::Delete($_.FullName) } catch { $fallos += [pscustomobject]@{ Archivo = $_.FullName; Error = $_.Exception.Message } }
    }
    if ($fallos.Count -gt 0) {
        Write-Host "  Archivos que NO se pueden borrar ($($fallos.Count)); primeros 15:" -ForegroundColor Red
        $fallos | Select-Object -First 15 | Format-List
    }
    # c) rutas largas / casos raros: espejo con un directorio vacio y rd con prefijo \\?\
    $vacio = Join-Path $env:TEMP ("vacio-" + [guid]::NewGuid().ToString("N")); New-Item -ItemType Directory $vacio | Out-Null
    & robocopy $vacio $ruta /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
    Remove-Item $vacio -Force -ErrorAction SilentlyContinue
    & cmd.exe /c ('rd /s /q "\\?\' + $ruta + '"') 2>&1 | Out-Null
    return -not (Test-Path -LiteralPath $ruta)
}

Write-Host "`n[2] Borrando..." -ForegroundColor Cyan
$carpetas = @($programa)
$carpetas += Get-ChildItem (Split-Path $programa) -Directory -Filter "DARK.previous-*" -ErrorAction SilentlyContinue | ForEach-Object FullName
foreach ($c in $carpetas | Select-Object -Unique) {
    if (-not (Test-Path -LiteralPath $c)) { Write-Host "no existe (nada que borrar): $c"; continue }
    Write-Host "borrando: $c"
    if (Intentar-Borrar $c) { Write-Host "BORRADO: $c" -ForegroundColor Green }
    else {
        Write-Host "NO se pudo borrar: $c" -ForegroundColor Red
        $quedan = @(Get-ChildItem -LiteralPath $c -Recurse -Force -ErrorAction SilentlyContinue)
        Write-Host "  quedan $($quedan.Count) elementos. Propietario y permisos de la carpeta:"
        try { (Get-Acl -LiteralPath $c).Access | Select-Object IdentityReference, FileSystemRights, AccessControlType | Format-Table -AutoSize } catch { Write-Host "  no se pudo leer el ACL: $($_.Exception.Message)" }
        $quedan | Select-Object -First 10 FullName, Attributes | Format-List
    }
}
if (Test-Path -LiteralPath $acceso) { Remove-Item -LiteralPath $acceso -Force -ErrorAction SilentlyContinue; Write-Host "borrado acceso del menu Inicio" }
if (Test-Path $clave) { Remove-Item $clave -Recurse -Force -ErrorAction SilentlyContinue; Write-Host "borrada la clave de desinstalacion" }
if ($TambienDatos) {
    # La contrasena de acceso y la cache de Electron viven en AppData\Roaming, fuera de %LOCALAPPDATA%\DARK.
    $electron = Join-Path $env:APPDATA "dark-desktop-shell"
    if (Test-Path -LiteralPath $electron) { if (Intentar-Borrar $electron) { Write-Host "BORRADA la contrasena y datos de Electron: $electron" -ForegroundColor Green } else { Write-Host "NO se pudo borrar: $electron" -ForegroundColor Red } }
    if (-not (Test-Path -LiteralPath $datos)) { Write-Host "no existe (nada que borrar): $datos" }
    elseif (Intentar-Borrar $datos) { Write-Host "BORRADOS los datos: $datos" -ForegroundColor Green } else { Write-Host "NO se pudieron borrar los datos: $datos" -ForegroundColor Red }
} else { Write-Host "Se conservan los datos en $datos (usa -TambienDatos para borrarlos)." }

if (Test-Path -LiteralPath $programa) {
    Write-Host "`nLa carpeta sigue existiendo. El detalle esta arriba y en: $registro" -ForegroundColor Red
    Write-Host "Avisa en el chat 'limpieza fallida' y lo leo desde alli."
} else { Write-Host "`nListo: D.A.R.K. quedo desinstalado de este perfil." -ForegroundColor Green }
Stop-Transcript | Out-Null
