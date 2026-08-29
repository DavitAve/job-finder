param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$services = @(
    [pscustomobject]@{ Name = "Frontend"; Port = 5173; Url = "http://127.0.0.1:5173"; Marker = "Frontend Job Finder"; CommandMarker = "vite" },
    [pscustomobject]@{ Name = "Backend"; Port = 8000; Url = "http://127.0.0.1:8000/api/health"; Marker = '"status":"ok"'; CommandMarker = "job_finder" }
)

function Test-ExpectedEndpoint($Service) {
    try {
        $response = Invoke-WebRequest -Uri $Service.Url -UseBasicParsing -TimeoutSec 1
        return $response.Content.Contains($Service.Marker)
    }
    catch {
        return $false
    }
}

function Test-ExpectedProcess([int]$ProcessId, $Service) {
    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId"
        $signature = "$($process.ExecutablePath) $($process.CommandLine)"
        return $signature.IndexOf($projectRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and $signature.IndexOf($Service.CommandMarker, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    }
    catch {
        return $false
    }
}

$failed = $false
foreach ($service in $services) {
    $listeners = Get-NetTCPConnection -LocalPort $service.Port -State Listen -ErrorAction SilentlyContinue
    $processIds = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($processIds.Count -eq 0) {
        Write-Host "$($service.Name) is not running (port $($service.Port))." -ForegroundColor DarkGray
        continue
    }
    $endpointMatches = Test-ExpectedEndpoint $service
    foreach ($processId in $processIds) {
        if (-not $Force -and -not $endpointMatches -and -not (Test-ExpectedProcess $processId $service)) {
            Write-Host "Refusing to stop PID $processId on port $($service.Port): it does not look like Job Finder. Use -Force only if this is the intended process." -ForegroundColor Red
            $failed = $true
            continue
        }
        try {
            Stop-Process -Id $processId -Force -ErrorAction Stop
            Write-Host "$($service.Name) stopped (PID $processId)." -ForegroundColor Green
        }
        catch {
            Write-Host "Cannot stop $($service.Name) PID $processId`: $($_.Exception.Message)" -ForegroundColor Red
            $failed = $true
        }
    }
}

foreach ($attempt in 1..40) {
    $remaining = $services | Where-Object {
        $null -ne (Get-NetTCPConnection -LocalPort $_.Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    }
    if (-not $remaining) { break }
    Start-Sleep -Milliseconds 250
}

$occupied = $services | Where-Object {
    $null -ne (Get-NetTCPConnection -LocalPort $_.Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
}
if ($occupied) {
    Write-Host "Some ports are still occupied: $($occupied.Port -join ', ')." -ForegroundColor Red
    $failed = $true
}
if ($failed) { exit 1 }
Write-Host "Job Finder is stopped." -ForegroundColor Cyan
exit 0
