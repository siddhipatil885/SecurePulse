"""Sanitized deployment inventory, baseline, source checks, and restart recovery.

Requires only Python's standard library; Docker/FFmpeg are used on the host.
No credentials, container environments, private images, or raw logs are emitted.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.request import Request, urlopen

if __package__:
    from .probe_rtsp import probe
else:
    from probe_rtsp import probe

BACKEND = Path(__file__).resolve().parents[1]


def command(arguments: list[str], timeout: float = 30) -> str:
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Docker/FFmpeg stderr can contain credentials or private source URLs.
        raise RuntimeError(f"{Path(arguments[0]).name} exited with code {result.returncode}")
    return result.stdout


def get_json(base: str, path: str, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with urlopen(Request(base.rstrip("/") + path, headers=headers), timeout=5) as response:
        return json.load(response)


def inventory() -> list[dict]:
    ids = command(["docker", "ps", "-aq"]).split()
    if not ids:
        return []
    records = json.loads(command(["docker", "inspect", *ids]))
    output = []
    for item in records:
        labels = item["Config"].get("Labels") or {}
        if not labels.get("com.docker.compose.project"):
            continue
        bindings = item.get("HostConfig", {}).get("PortBindings") or {}
        output.append({
            "name": item["Name"].lstrip("/"),
            "project": labels.get("com.docker.compose.project"),
            "service": labels.get("com.docker.compose.service"),
            "source_directory": labels.get("com.docker.compose.project.working_dir"),
            "compose_files": labels.get("com.docker.compose.project.config_files"),
            "image": item["Config"]["Image"],
            "state": item["State"]["Status"],
            "health": item["State"].get("Health", {}).get("Status"),
            "ports": bindings,
            "all_interface_ports": [port for port, hosts in bindings.items()
                                    if any(host["HostIp"] in ("", "0.0.0.0", "::") for host in (hosts or []))],
            "mounts": [{key: mount.get(key) for key in ("Type", "Name", "Source", "Destination", "RW")}
                       for mount in item.get("Mounts", [])],
        })
    return output


def edge_sample(base: str) -> dict:
    data = get_json(base, "/health/edge")
    result = {key: data.get(key) for key in (
        "status", "mqtt", "frigate", "detection_fps", "queue_depth", "queue_capacity",
        "queue_rejections", "processing_failures", "invalid_event_count", "adapter_delivery_failures", "last_event_at",
    )}
    result["cameras"] = {name: {key: camera.get(key) for key in (
        "status", "camera_fps", "process_fps", "detection_enabled",
    )} for name, camera in data.get("cameras", {}).items()}
    return result


def healthy(base: str, cameras: set[str]) -> bool:
    try:
        ready = get_json(base, "/health/ready")
        edge = edge_sample(base)
        observed = edge["cameras"]
        return (ready.get("status") == "ok" and edge["status"] == "ok"
                and cameras.issubset(observed)
                and all(observed[name]["status"] == "online" and observed[name]["detection_enabled"] is True
                        for name in cameras))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def source_check(args) -> tuple[dict, bool]:
    checks = []
    for path in args.paths.split(","):
        item = probe(args.rtsp_host, args.rtsp_port, path)
        if item["ready"]:
            # Decode without saving imagery; blackdetect only emits timing data.
            # Do not print FFmpeg's stderr: it can contain private source URLs.
            process = subprocess.run([
                "ffmpeg", "-hide_banner", "-nostdin", "-rtsp_transport", "tcp",
                "-i", f"rtsp://{args.rtsp_host}:{args.rtsp_port}/{path}",
                "-t", "8", "-an", "-vf", "blackdetect=d=1:pix_th=0.10:pic_th=0.98",
                "-progress", "pipe:1", "-f", "null", "-",
            ], capture_output=True, text=True, timeout=20)
            times = re.findall(r"out_time_us=(\d+)", process.stdout)
            item["decoded_seconds"] = max((int(value) / 1_000_000 for value in times), default=0)
            item["black_detected"] = "black_start:" in process.stderr
            item["decoded"] = process.returncode == 0 and item["decoded_seconds"] >= 5
        checks.append(item)
    passed = all(item.get("decoded") and not item.get("black_detected") for item in checks)
    return {"streams": checks, "status": "pass" if passed else "fail"}, passed


def baseline(args) -> tuple[dict, bool]:
    samples = []
    end = time.monotonic() + args.duration
    expected = set(args.cameras.split(","))
    while True:
        sample = {"observed_at": datetime.now(timezone.utc).isoformat()}
        try:
            sample["edge"] = edge_sample(args.backend)
            sample["ready"] = get_json(args.backend, "/health/ready").get("status") == "ok"
            events = get_json(args.backend, "/api/v1/events?page=1&page_size=1", os.getenv("SECUREPULSE_OPERATOR_TOKEN"))
            sample["persisted_events"] = events["total"]
            stats = command(["docker", "stats", "--no-stream", "--format", "{{json .}}"], timeout=20)
            sample["containers"] = [{key: item.get(key) for key in ("Name", "CPUPerc", "MemUsage", "MemPerc", "PIDs")}
                                    for item in (json.loads(line) for line in stats.splitlines() if line)]
        except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
            sample["error"] = type(error).__name__
        sample["monotonic_seconds"] = time.monotonic()
        samples.append(sample)
        if time.monotonic() >= end:
            break
        time.sleep(min(args.interval, max(0, end - time.monotonic())))
    passed = all(
        "error" not in sample and sample["ready"] and sample["edge"]["status"] == "ok"
        and expected.issubset(sample["edge"]["cameras"])
        and all(sample["edge"]["cameras"][name].get("detection_enabled") is True for name in expected)
        and all(sample["edge"][key] == 0 for key in (
            "queue_rejections", "processing_failures", "invalid_event_count", "adapter_delivery_failures"))
        for sample in samples
    )
    throughput = None
    if len(samples) > 1 and all("persisted_events" in sample for sample in (samples[0], samples[-1])):
        elapsed = samples[-1]["monotonic_seconds"] - samples[0]["monotonic_seconds"]
        delta = samples[-1]["persisted_events"] - samples[0]["persisted_events"]
        throughput = delta / elapsed if elapsed > 0 and delta >= 0 else None
    for sample in samples:
        sample.pop("monotonic_seconds")
    return {"status": "pass" if passed else "fail", "persisted_events_per_second": throughput,
            "throughput_definition": "Net API event-row growth; excludes MQTT updates and deduplicated receipts",
            "samples": samples}, passed


def recover(args) -> tuple[dict, bool]:
    expected = set(args.cameras.split(","))
    if not healthy(args.backend, expected):
        return {"status": "fail", "reason": "healthy_baseline_required"}, False
    compose = ["docker", "compose", "--project-name", args.project, "--env-file", str(args.env_file),
               "-f", str(BACKEND / "deployment/docker-compose.yml")]
    # Resolve the exact running target; never switch Compose projects implicitly.
    ids = command([*compose, "ps", "-q", args.restart_service]).split()
    if len(ids) != 1:
        return {"status": "fail", "reason": "expected_one_running_target"}, False
    item = json.loads(command(["docker", "inspect", ids[0]]))[0]
    labels = item["Config"].get("Labels") or {}
    if (labels.get("com.docker.compose.project") != args.project
            or labels.get("com.docker.compose.service") != args.restart_service):
        return {"status": "fail", "reason": "target_identity_mismatch"}, False
    initial = edge_sample(args.backend)
    start = time.monotonic()
    command([*compose, "restart", args.restart_service], timeout=60)
    consecutive = 0
    while time.monotonic() - start < args.duration:
        consecutive = consecutive + 1 if healthy(args.backend, expected) else 0
        if consecutive >= 3:
            final = edge_sample(args.backend)
            # Backend counters reset on backend restart; broker restart must not add failures.
            passed = all(final[key] <= (0 if args.restart_service == "backend" else initial[key]) for key in (
                "queue_rejections", "processing_failures", "invalid_event_count", "adapter_delivery_failures"))
            return {"status": "pass" if passed else "fail", "service": args.restart_service,
                    "project": args.project, "recovery_seconds": round(time.monotonic() - start, 2),
                    "edge": final, "fresh_person_event": "requires_walk_through"}, passed
        time.sleep(args.interval)
    return {"status": "fail", "reason": "recovery_timeout", "service": args.restart_service}, False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inventory", "baseline", "sources", "recovery"))
    parser.add_argument("--backend", default="http://127.0.0.1:18000")
    parser.add_argument("--duration", type=float, default=120)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--cameras", default="front_door,laptop_camera")
    parser.add_argument("--rtsp-host", default="127.0.0.1")
    parser.add_argument("--rtsp-port", type=int, default=18554)
    parser.add_argument("--paths", default="live,webcam")
    parser.add_argument("--project", help="Required exact Compose project for recovery")
    parser.add_argument("--env-file", type=Path, default=BACKEND / "deployment/.env")
    parser.add_argument("--restart-service", choices=("mqtt", "backend"), help="Explicitly authorize restarting this service")
    args = parser.parse_args()
    if args.duration <= 0 or not 0 < args.interval <= 60:
        parser.error("duration must be positive and interval must be in (0, 60]")
    if args.mode == "recovery" and (not args.project or not args.restart_service):
        parser.error("recovery requires --project and --restart-service; it restarts that service")
    required = "ffmpeg" if args.mode == "sources" else "docker"
    if not shutil.which(required):
        print(json.dumps({"status": "blocked", "reason": f"{required}_not_installed"}))
        return 2
    try:
        if args.mode == "inventory":
            result, passed = {"containers": inventory(), "status": "observed"}, True
        else:
            result, passed = {"baseline": baseline, "sources": source_check, "recovery": recover}[args.mode](args)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result, passed = {"status": "blocked", "reason": type(error).__name__}, False
    print(json.dumps({"observed_at": datetime.now(timezone.utc).isoformat(), **result}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
