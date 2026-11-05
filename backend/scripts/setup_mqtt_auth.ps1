param(
    [string]$MosquittoImage = "eclipse-mosquitto:2.0.21"
)

$ErrorActionPreference = "Stop"
$configDir = Join-Path $PSScriptRoot "..\deployment\mosquitto\config"
$configDir = (Resolve-Path $configDir).Path
$passwordFile = Join-Path $configDir "passwordfile"
if (Test-Path $passwordFile) {
    throw "Password file already exists. Preserve it; use mosquitto_passwd without -c to update a specific account during maintenance."
}

Write-Host "Create a password for Frigate's publish-only MQTT account."
docker run --rm -it --mount "type=bind,source=$configDir,target=/mosquitto/config" $MosquittoImage mosquitto_passwd -c /mosquitto/config/passwordfile frigate
if ($LASTEXITCODE -ne 0) { throw "Could not create the Frigate MQTT password." }

Write-Host "Create a password for SecurePulse's read-only MQTT account."
docker run --rm -it --mount "type=bind,source=$configDir,target=/mosquitto/config" $MosquittoImage mosquitto_passwd /mosquitto/config/passwordfile securepulse
if ($LASTEXITCODE -ne 0) { throw "Could not add the SecurePulse MQTT password." }

Write-Host "Password file created at $passwordFile. Copy the same passwords into deployment/.env; do not commit either file."
