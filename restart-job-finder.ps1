param(
    [switch]$NoBrowser,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

& (Join-Path $projectRoot "stop-job-finder.ps1") -Force:$Force
if ($LASTEXITCODE -ne 0) {
    Write-Host "Restart cancelled because one or more processes could not be stopped." -ForegroundColor Red
    exit $LASTEXITCODE
}

& (Join-Path $projectRoot "start-job-finder.ps1") -NoBrowser:$NoBrowser
exit $LASTEXITCODE
