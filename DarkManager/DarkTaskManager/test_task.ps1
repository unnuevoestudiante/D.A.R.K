$json = @{
    descripcion = "prueba diagnostico"
    prioridad = "Alta"
    modulo = "Nucleo"
    pasos = @()
} | ConvertTo-Json

Write-Host "Enviando JSON:"
Write-Host $json

try {
    $response = Invoke-RestMethod -Uri "http://localhost:5051/tasks" -Method POST -ContentType "application/json" -Body $json
    Write-Host "Respuesta exitosa:"
    Write-Host ($response | ConvertTo-Json)
} catch {
    Write-Host "Error:"
    Write-Host $_.Exception.Message
    Write-Host $_.Exception.Response
}