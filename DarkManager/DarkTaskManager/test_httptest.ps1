# Test directo con HttpClient
Add-Type -AssemblyName System.Net.Http

$json = '{"descripcion":"prueba diagnostico","prioridad":"Alta","modulo":"Nucleo","pasos":[]}'

$client = New-Object System.Net.Http.HttpClient
$content = New-Object System.Net.Http.StringContent($json, [System.Text.Encoding]::UTF8, "application/json")

try {
    $response = $client.PostAsync("http://localhost:5051/tasks", $content).Result
    $responseString = $response.Content.ReadAsStringAsync().Result
    Write-Host "Status: $($response.StatusCode)"
    Write-Host "Response: $responseString"
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}