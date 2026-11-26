$json = '{"descripcion":"prueba diagnostico","prioridad":"Alta","modulo":"Nucleo","pasos":[]}'

try {
    $response = Invoke-RestMethod -Uri "http://localhost:5051/tasks" -Method POST -ContentType "application/json" -Body $json -TimeoutSec 5
    Write-Host "Exito: $($response | ConvertTo-Json)"
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    if ($_.Exception.Response) {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        $responseBody = $reader.ReadToEnd()
        Write-Host "Response body: $responseBody"
    }
}