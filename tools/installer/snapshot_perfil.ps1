<#
.SYNOPSIS
  Foto del estado del perfil de Windows para probar el instalador de D.A.R.K.
  sin máquina virtual. Ejecutar en el SEGUNDO perfil, antes y después de cada paso.

.EXAMPLE
  .\snapshot_perfil.ps1 -Etiqueta antes
  .\snapshot_perfil.ps1 -Etiqueta despues-instalar
  .\snapshot_perfil.ps1 -Comparar antes despues-instalar
#>
param(
    [string]$Etiqueta,
    [string[]]$Comparar,
    [string]$Carpeta
)

$carpeta = if ($Carpeta) { $Carpeta } else { Join-Path $env:USERPROFILE "DarkPrueba" }
New-Item -ItemType Directory -Force $carpeta | Out-Null

function Tomar-Foto {
    $herramientas = foreach ($n in "python", "py", "node", "npm", "dotnet", "ollama", "git", "ffmpeg") {
        $c = Get-Command $n -ErrorAction SilentlyContinue | Select-Object -First 1
        [pscustomobject]@{ nombre = $n; ruta = if ($c) { $c.Source } else { $null } }
    }
    $puertos = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        [pscustomobject]@{ puerto = $_.LocalPort; direccion = $_.LocalAddress; proceso = $p.ProcessName; pid = $_.OwningProcess }
    } | Sort-Object puerto, proceso -Unique
    $procesos = Get-Process | Where-Object { $_.ProcessName -match "dark|electron|node|python|ollama|llama" } |
        Select-Object ProcessName, Id, @{n = "ruta"; e = { try { $_.Path } catch { $null } } }
    $localApp = $env:LOCALAPPDATA
    $claveDesinstalar = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\DARK"
    [pscustomobject]@{
        fecha        = (Get-Date).ToString("s")
        usuario      = $env:USERNAME
        herramientas = $herramientas
        variablesDark = Get-ChildItem Env: | Where-Object { $_.Name -match "^(DARK_|ACCESO_)" } | ForEach-Object { $_.Name }
        puertos      = $puertos
        procesos     = $procesos
        existe       = [pscustomobject]@{
            app      = Test-Path (Join-Path $localApp "Programs\DARK")
            datos    = Test-Path (Join-Path $localApp "DARK")
            registro = Test-Path $claveDesinstalar
            menuInicio = [bool](Get-ChildItem (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs") -Recurse -Filter "*DARK*" -ErrorAction SilentlyContinue)
        }
    }
}

if ($Comparar) {
    $a = Get-Content (Join-Path $carpeta "snapshot-$($Comparar[0]).json") -Raw | ConvertFrom-Json
    $b = Get-Content (Join-Path $carpeta "snapshot-$($Comparar[1]).json") -Raw | ConvertFrom-Json
    Write-Host "== Puertos nuevos ==" -ForegroundColor Cyan
    $antes = @($a.puertos | ForEach-Object { "$($_.puerto)|$($_.proceso)" })
    $b.puertos | Where-Object { "$($_.puerto)|$($_.proceso)" -notin $antes } | Format-Table puerto, direccion, proceso, pid -AutoSize
    Write-Host "== Procesos nuevos ==" -ForegroundColor Cyan
    $idsAntes = @($a.procesos | ForEach-Object { $_.Id })
    $b.procesos | Where-Object { $_.Id -notin $idsAntes } | Format-Table ProcessName, Id, ruta -AutoSize
    Write-Host "== Presencia de la instalación ==" -ForegroundColor Cyan
    Write-Host "antes  :" ($a.existe | ConvertTo-Json -Compress)
    Write-Host "despues:" ($b.existe | ConvertTo-Json -Compress)
    return
}

if (-not $Etiqueta) { throw "Indica -Etiqueta o -Comparar." }
$ruta = Join-Path $carpeta "snapshot-$Etiqueta.json"
Tomar-Foto | ConvertTo-Json -Depth 6 | Set-Content $ruta -Encoding utf8
Write-Host "Foto guardada en $ruta"
$f = Get-Content $ruta -Raw | ConvertFrom-Json
Write-Host "Herramientas globales visibles en ESTE perfil (lo ideal para la prueba es que no haya ninguna):"
$f.herramientas | Format-Table nombre, ruta -AutoSize
