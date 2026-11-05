param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9][a-z0-9_-]*$')]
    [string]$ProjectName,
    [string]$Python = "python",
    [string]$BackendUrl = "http://127.0.0.1:18000",
    [int]$BaselineSeconds = 120,
    [switch]$RestartRecovery
)

# Run on the camera PC, after deploying and starting real /live + /webcam
# publishers. This script never deploys, migrates, stops publishers, or deletes
# data. -RestartRecovery opts in to restarting mqtt and backend, in that order.
$ErrorActionPreference = "Stop"
if ($BaselineSeconds -lt 10) { throw "Use at least ten seconds for a baseline." }
foreach ($tool in @($Python, "docker", "ffmpeg")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Required tool unavailable: $tool" }
}
$backendDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $backendDir "deployment/.env"
if (-not (Test-Path $envFile)) { throw "Create deployment/.env with the existing host configuration first." }
$composeArgs = @("compose", "--project-name", $ProjectName, "--env-file", $envFile,
    "-f", (Join-Path $backendDir "deployment/docker-compose.yml"))
& docker @composeArgs config --quiet
if ($LASTEXITCODE -ne 0) { throw "Compose validation failed." }
& docker @composeArgs ps
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the selected project." }

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$evidenceDir = Join-Path $backendDir "operational-evidence/$stamp"
New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null
$script = Join-Path $PSScriptRoot "edge_operations.py"
$failed = $false

function Invoke-Evidence {
    param([string]$Name, [string[]]$Arguments)
    $result = & $Python $script @Arguments
    $exitCode = $LASTEXITCODE
    $result | Set-Content -Encoding utf8 (Join-Path $evidenceDir "$Name.json")
    if ($exitCode -ne 0) {
        $script:failed = $true
        Write-Host "FAIL/BLOCKED $Name (see sanitized evidence)"
    } else { Write-Host "PASS $Name" }
}

Invoke-Evidence "inventory" @("inventory")
Invoke-Evidence "sources" @("sources")
Invoke-Evidence "baseline" @("baseline", "--backend", $BackendUrl, "--duration", "$BaselineSeconds")
if ($RestartRecovery -and -not $failed) {
    foreach ($service in @("mqtt", "backend")) {
        Invoke-Evidence "recovery-$service" @("recovery", "--project", $ProjectName,
            "--env-file", $envFile, "--backend", $BackendUrl, "--restart-service", $service)
    }
} elseif ($RestartRecovery) {
    Write-Host "SKIP restart recovery: fix the failed inventory/source/baseline checks first."
}
Write-Host "Evidence: $evidenceDir"
Write-Host "Next: perform both camera walk-throughs and browser playback/overlay checks in docs/END_TO_END_TEST_REPORT.md."
if ($failed) { exit 1 }
