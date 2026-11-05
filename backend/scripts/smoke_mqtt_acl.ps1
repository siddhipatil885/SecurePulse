param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9][a-z0-9_-]*$')]
    [string]$ProjectName
)

$ErrorActionPreference = "Stop"
$backendDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composeArgs = @("compose", "--project-name", $ProjectName, "--env-file", (Join-Path $backendDir "deployment/.env"), "-f", (Join-Path $backendDir "deployment/docker-compose.yml"), "exec", "-T", "mqtt", "sh", "-c")

function Invoke-AclCheck {
    param(
        [string]$Name,
        [string]$Command,
        [bool]$ExpectedSuccess
    )
    & docker @composeArgs $Command
    $succeeded = $LASTEXITCODE -eq 0
    if ($succeeded -ne $ExpectedSuccess) {
        throw "MQTT ACL check failed: $Name"
    }
    Write-Host "PASS $Name"
}

# Verify control-topic delivery rather than trusting mosquitto_pub's exit code:
# MQTT 3.1.1 brokers may silently drop an unauthorized publish.
Invoke-AclCheck "Frigate can publish and receive control-shaped probe" 'set -eu; (mosquitto_sub -h 127.0.0.1 -u frigate -P "$MQTT_FRIGATE_PASSWORD" -t frigate/engineer1/acl-probe/set -C 1 -W 3 >/dev/null) & sub=$!; sleep 0.2; mosquitto_pub -q 1 -h 127.0.0.1 -u frigate -P "$MQTT_FRIGATE_PASSWORD" -t frigate/engineer1/acl-probe/set -m probe; wait "$sub"' $true
Invoke-AclCheck "Backend can subscribe to event topic" 'mosquitto_sub -E -h 127.0.0.1 -u securepulse -P "$MQTT_BACKEND_PASSWORD" -t frigate/events' $true
Invoke-AclCheck "Backend cannot publish camera control" 'set -eu; (mosquitto_sub -h 127.0.0.1 -u frigate -P "$MQTT_FRIGATE_PASSWORD" -t frigate/engineer1/acl-probe/set -C 1 -W 2 >/dev/null) & sub=$!; sleep 0.2; mosquitto_pub -q 1 -h 127.0.0.1 -u securepulse -P "$MQTT_BACKEND_PASSWORD" -t frigate/engineer1/acl-probe/set -m probe; if wait "$sub"; then exit 1; else exit 0; fi' $true
Invoke-AclCheck "Frigate cannot read arbitrary probe topics" 'set -eu; (mosquitto_sub -h 127.0.0.1 -u frigate -P "$MQTT_FRIGATE_PASSWORD" -t frigate/engineer1/acl-probe -C 1 -W 2 >/dev/null) & sub=$!; sleep 0.2; mosquitto_pub -q 1 -h 127.0.0.1 -u frigate -P "$MQTT_FRIGATE_PASSWORD" -t frigate/engineer1/acl-probe -m probe; if wait "$sub"; then exit 1; else exit 0; fi' $true
Invoke-AclCheck "Invalid credentials are rejected" 'mosquitto_sub -E -h 127.0.0.1 -u securepulse -P invalid-password -t frigate/events' $false
Invoke-AclCheck "Anonymous access is rejected" 'mosquitto_sub -E -h 127.0.0.1 -t frigate/events' $false
