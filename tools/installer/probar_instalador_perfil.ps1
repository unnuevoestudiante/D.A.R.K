<#
.SYNOPSIS
  Prueba guiada del instalador Tester de D.A.R.K. en un segundo perfil de Windows.
  Un solo comando; guarda todo en C:\Users\Public\DarkResultados para leerlo desde el otro perfil.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File C:\Users\Public\DarkScripts\probar_instalador_perfil.ps1
#>
$publico   = "C:\Users\Public"
$bundle    = Join-Path $publico "DarkBundle"
$scripts   = Join-Path $publico "DarkScripts"
$resultados = Join-Path $publico "DarkResultados"
$snapshot  = Join-Path $scripts "snapshot_perfil.ps1"
New-Item -ItemType Directory -Force $resultados | Out-Null
$sello = Get-Date -Format "yyyyMMdd-HHmmss"
Start-Transcript -Path (Join-Path $resultados "transcripcion-$sello.txt") | Out-Null

function Titulo($texto) { Write-Host "`n=== $texto ===" -ForegroundColor Cyan }
function Pausa($texto)  { Read-Host "`n>> $texto (pulsa Enter)" | Out-Null }
# Ruta completa: con el PATH reducido, "powershell" a secas no se encontraria.
$ps = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
function Foto($etiqueta) { & $ps -NoProfile -ExecutionPolicy Bypass -File $snapshot -Etiqueta $etiqueta -Carpeta $resultados }
function Comparar($a, $b) { & $ps -NoProfile -ExecutionPolicy Bypass -File $snapshot -Comparar $a, $b -Carpeta $resultados }

try {
    Titulo "0. Entorno"
    Write-Host "Perfil: $env:USERNAME"
    if ($env:USERNAME -eq "samue") {
        Write-Host "AVISO: parece tu perfil principal. Esta prueba esta pensada para el SEGUNDO perfil." -ForegroundColor Yellow
        $seguir = Read-Host "Continuar de todos modos? (s/n)"
        if ($seguir -notmatch '^[sS]') { throw "Cancelado: ejecuta el script en el segundo perfil." }
    }
    if (-not (Test-Path (Join-Path $bundle "DarkInstaller.exe"))) {
        throw "No encuentro $bundle\DarkInstaller.exe. Copia primero la carpeta dark-tester-bundle a $bundle."
    }

    Titulo "1. Foto inicial (antes de instalar, con el PATH normal del perfil)"
    Foto "antes"

    # PATH reducido a partir de aqui, para que D.A.R.K. no se apoye en Python, Node o .NET globales.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    Write-Host "PATH reducido a: $env:PATH"

    Titulo "2. Verificacion de hashes del bundle"
    $fallos = 0
    foreach ($linea in Get-Content (Join-Path $bundle "SHA256SUMS.txt")) {
        if ($linea -notmatch '^([0-9a-fA-F]{64})\s+(.+)$') { continue }
        $esperado = $Matches[1].ToLower(); $nombre = $Matches[2].Trim()
        $archivo = Join-Path $bundle $nombre
        if (-not (Test-Path $archivo)) { Write-Host "FALTA   $nombre" -ForegroundColor Red; $fallos++; continue }
        $real = (Get-FileHash $archivo -Algorithm SHA256).Hash.ToLower()
        if ($real -eq $esperado) { Write-Host "OK      $nombre" -ForegroundColor Green }
        else { Write-Host "DISTINTO $nombre" -ForegroundColor Red; $fallos++ }
    }
    if ($fallos -gt 0) { throw "Hay $fallos archivos con problemas. No continuo: vuelve a copiar el bundle." }

    Titulo "3. Instalador"
    Write-Host "Se abrira el instalador. Escribe el codigo de acceso, lee las condiciones,"
    Write-Host "abre la licencia, marca la casilla e instala. Al terminar, cierra el instalador."
    Write-Host "Mira: botones sin textos duplicados, boton de maximizar, bordes redimensionables."
    Pausa "Listo para abrir el instalador"
    Start-Process (Join-Path $bundle "DarkInstaller.exe") -Wait

    Titulo "4. Foto despues de instalar"
    Foto "despues-instalar"
    Comparar "antes" "despues-instalar"
    $app = Join-Path $env:LOCALAPPDATA "Programs\DARK\app"
    $supervisor = Join-Path $app "DarkSupervisor.exe"
    Write-Host "DarkSupervisor.exe existe: $(Test-Path $supervisor)"
    if (Test-Path $app) {
        $mb = [math]::Round((Get-ChildItem $app -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1MB)
        Write-Host "Tamano instalado: $mb MB"
    }
    if (-not (Test-Path $supervisor)) { throw "La instalacion no dejo DarkSupervisor.exe. Reviso el resultado." }

    Titulo "5. Primera apertura de D.A.R.K."
    Write-Host "Se abrira D.A.R.K. Observa: si aparece la ventana, si pide crear contrasena, errores."
    Write-Host "Opcional: di o escribe 'registro facial' y comprueba que la camara NO se enciende sin aceptar."
    Pausa "Listo para abrir D.A.R.K."
    Start-Process $supervisor -WorkingDirectory $app
    Pausa "Cuando D.A.R.K. este abierto y estable"
    Foto "con-dark-abierto"

    Titulo "6. Cierre"
    Write-Host "Cierra D.A.R.K. como lo haria un usuario normal."
    Pausa "Cuando lo hayas cerrado"
    Write-Host "Espero 15 segundos..."
    Start-Sleep -Seconds 15
    Foto "despues-cerrar"
    Comparar "antes" "despues-cerrar"
    $restos = Get-Process -Name DarkSupervisor, DarkManager, DarkTaskManager, electron -ErrorAction SilentlyContinue
    if ($restos) {
        Write-Host "ATENCION: quedan procesos de D.A.R.K.:" -ForegroundColor Red
        $restos | Format-Table ProcessName, Id, Path -AutoSize
    } else {
        Write-Host "Sin procesos de D.A.R.K. residuales." -ForegroundColor Green
    }
    $logs = Join-Path $env:LOCALAPPDATA "DARK\logs"
    if (Test-Path $logs) { Copy-Item $logs (Join-Path $resultados "logs-$sello") -Recurse -Force; Write-Host "Logs copiados a resultados." }

    Titulo "7. Desinstalar (opcional)"
    $r = Read-Host "Quieres probar la desinstalacion ahora? (s/n)"
    if ($r -match '^[sS]') {
        Write-Host "Se abrira Aplicaciones instaladas. Busca D.A.R.K., desinstala y confirma."
        Start-Process "ms-settings:appsfeatures"
        Pausa "Cuando la desinstalacion termine"
        Foto "despues-desinstalar"
        Comparar "antes" "despues-desinstalar"
    }
}
catch {
    Write-Host "`nERROR: $($_.Exception.Message)" -ForegroundColor Red
}
finally {
    Titulo "Fin"
    Write-Host "Resultados guardados en: $resultados"
    Write-Host "Avisa en el chat 'termine la prueba' y los leo desde alli."
    Stop-Transcript | Out-Null
}
