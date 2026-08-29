$ErrorActionPreference = "Stop"

$services = @(
    [pscustomobject]@{ Name = "Backend"; Port = 8000; Url = "http://127.0.0.1:8000/api/health"; Marker = '"status":"ok"' },
    [pscustomobject]@{ Name = "Frontend"; Port = 5173; Url = "http://127.0.0.1:5173"; Marker = "Frontend Job Finder" }
)

foreach ($service in $services) {
    $listener = Get-NetTCPConnection -LocalPort $service.Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $listener) {
        Write-Host ("{0,-9} STOPPED   port {1}" -f $service.Name, $service.Port) -ForegroundColor DarkGray
        continue
    }
    $healthy = $false
    try {
        $response = Invoke-WebRequest -Uri $service.Url -UseBasicParsing -TimeoutSec 2
        $healthy = $response.Content.Contains($service.Marker)
    }
    catch {
        $healthy = $false
    }
    if ($healthy) {
        Write-Host ("{0,-9} RUNNING   port {1}   PID {2}   {3}" -f $service.Name, $service.Port, $listener.OwningProcess, $service.Url) -ForegroundColor Green
    }
    else {
        Write-Host ("{0,-9} UNHEALTHY port {1}   PID {2}" -f $service.Name, $service.Port, $listener.OwningProcess) -ForegroundColor Yellow
    }
}
exit 0
