$ErrorActionPreference = "Stop"
$composeArgs = @("compose", "--project-name", "securepulse-person1", "--env-file", "deployment/.env", "-f", "deployment/docker-compose.yml", "exec", "-T", "mqtt", "sh", "-c")

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
Invoke-AclCheck "Frigate can publish and receive camera control" 'set -eu; (mosquitto_sub -h 127.0.0.1 -u frigate -P "$MQTT_FRIGATE_PASSWORD" -t frigate/front_door/detect/set -C 1 -W 3 >/dev/null) & sub=$!; sleep 0.2; mosquitto_pub -q 1 -h 127.0.0.1 -u frigate -P "$MQTT_FRIGATE_PASSWORD" -t frigate/front_door/detect/set -m ON; wait "$sub"' $true
Invoke-AclCheck "Backend can subscribe to event topic" 'mosquitto_sub -E -h 127.0.0.1 -u securepulse -P "$MQTT_BACKEND_PASSWORD" -t frigate/events' $true
Invoke-AclCheck "Backend cannot publish camera control" 'set -eu; (mosquitto_sub -h 127.0.0.1 -u frigate -P "$MQTT_FRIGATE_PASSWORD" -t frigate/front_door/detect/set -C 1 -W 2 >/dev/null) & sub=$!; sleep 0.2; mosquitto_pub -q 1 -h 127.0.0.1 -u securepulse -P "$MQTT_BACKEND_PASSWORD" -t frigate/front_door/detect/set -m ON; if wait "$sub"; then exit 1; else exit 0; fi' $true
Invoke-AclCheck "Frigate cannot read arbitrary probe topics" 'set -eu; (mosquitto_sub -h 127.0.0.1 -u frigate -P "$MQTT_FRIGATE_PASSWORD" -t frigate/engineer1/acl-probe -C 1 -W 2 >/dev/null) & sub=$!; sleep 0.2; mosquitto_pub -q 1 -h 127.0.0.1 -u frigate -P "$MQTT_FRIGATE_PASSWORD" -t frigate/engineer1/acl-probe -m probe; if wait "$sub"; then exit 1; else exit 0; fi' $true
Invoke-AclCheck "Invalid credentials are rejected" 'mosquitto_sub -E -h 127.0.0.1 -u securepulse -P invalid-password -t frigate/events' $false
