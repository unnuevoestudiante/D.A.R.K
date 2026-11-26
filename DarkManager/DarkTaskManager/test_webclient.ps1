$json = '{"descripcion":"prueba diagnostico","prioridad":"Alta","modulo":"Nucleo","pasos":[]}'

$webClient = New-Object System.Net.WebClient
$webClient.Headers.Add("Content-Type", "application/json")

try {
    $response = $webClient.UploadString("http://localhost:5051/tasks", "POST", $json)
    Write-Host "Exito: $response"
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    Write-Host "Status: $($_.Exception.Status)"
}