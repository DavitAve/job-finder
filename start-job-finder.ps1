param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRoot = Join-Path $projectRoot "backend"
$frontendRoot = Join-Path $projectRoot "frontend"
$pythonPath = Join-Path $backendRoot ".venv\Scripts\python.exe"
$logRoot = Join-Path $projectRoot ".logs"

function Test-HttpEndpoint([string]$Url, [string]$ExpectedText) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 1
        return $response.Content.Contains($ExpectedText)
    }
    catch {
        return $false
    }
}

function Test-PortListener([int]$Port) {
    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Backend environment not found: $pythonPath. Create it with: py -V:3.13 -m venv backend\.venv"
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "node_modules"))) {
    throw "Frontend dependencies are not installed. Run: Set-Location frontend; npm.cmd install"
}

New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

if (Test-HttpEndpoint "http://127.0.0.1:8000/api/health" '"status":"ok"') {
    Write-Host "Backend is already running: http://127.0.0.1:8000" -ForegroundColor DarkYellow
}
else {
    if (Test-PortListener 8000) {
        throw "Port 8000 is occupied by another or unhealthy process. Run .\status-job-finder.cmd, then .\stop-job-finder.cmd -Force if appropriate."
    }
    & $pythonPath -m job_finder db-upgrade
    if ($LASTEXITCODE -ne 0) {
        throw "Database migration failed. Check the command output above."
    }
    Start-Process -FilePath $pythonPath `
        -ArgumentList "-m", "job_finder", "serve" `
        -WorkingDirectory $backendRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logRoot "backend.out.log") `
        -RedirectStandardError (Join-Path $logRoot "backend.err.log")

    $backendReady = $false
    foreach ($attempt in 1..30) {
        Start-Sleep -Milliseconds 500
        if (Test-HttpEndpoint "http://127.0.0.1:8000/api/health" '"status":"ok"') {
            $backendReady = $true
            break
        }
    }
    if (-not $backendReady) {
        throw "Backend did not start. Check .logs\backend.err.log (port 8000 may be occupied)."
    }
    Write-Host "Backend started: http://127.0.0.1:8000" -ForegroundColor Green
}

if (Test-HttpEndpoint "http://127.0.0.1:5173" "Frontend Job Finder") {
    Write-Host "Frontend is already running: http://127.0.0.1:5173" -ForegroundColor DarkYellow
}
else {
    if (Test-PortListener 5173) {
        throw "Port 5173 is occupied by another or unhealthy process. Run .\status-job-finder.cmd, then .\stop-job-finder.cmd -Force if appropriate."
    }
    $npmPath = (Get-Command npm.cmd -ErrorAction Stop).Source
    Start-Process -FilePath $npmPath `
        -ArgumentList "run", "dev", "--", "--host", "127.0.0.1" `
        -WorkingDirectory $frontendRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logRoot "frontend.out.log") `
        -RedirectStandardError (Join-Path $logRoot "frontend.err.log")

    $frontendReady = $false
    foreach ($attempt in 1..30) {
        Start-Sleep -Milliseconds 500
        if (Test-HttpEndpoint "http://127.0.0.1:5173" "Frontend Job Finder") {
            $frontendReady = $true
            break
        }
    }
    if (-not $frontendReady) {
        throw "Frontend did not start. Check .logs\frontend.err.log (port 5173 may be occupied)."
    }
    Write-Host "Frontend started: http://127.0.0.1:5173" -ForegroundColor Green
}

if (-not $NoBrowser) {
    Start-Process "http://127.0.0.1:5173"
}

Write-Host "Job Finder is ready. Logs: $logRoot" -ForegroundColor Cyan
exit 0
