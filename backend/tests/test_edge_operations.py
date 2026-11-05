"""Operational checks must reject absent/broken streams and sanitize inventory."""

import json
import socket
import threading
from types import SimpleNamespace

import pytest

from scripts import edge_operations as operations
from scripts.probe_rtsp import probe, state_ready


def serve(response: bytes):
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def run():
        try:
            with server:
                connection, _ = server.accept()
                with connection:
                    connection.settimeout(2)
                    connection.recv(4096)
                    # Exercise a body that arrives separately from its header.
                    head, separator, body = response.partition(b"\r\n\r\n")
                    connection.sendall(head + separator)
                    if body:
                        connection.sendall(body)
        except (OSError, TimeoutError):
            pass

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return port, thread


@pytest.mark.parametrize("body,ready", [(b"v=0\r\nm=video 0 RTP/AVP 96\r\n", True),
                                       (b"v=0\r\nm=audio 0 RTP/AVP 0\r\n", False)])
def test_rtsp_requires_video_sdp(body, ready):
    port, thread = serve(b"RTSP/1.0 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
    result = probe("127.0.0.1", port, "live")
    thread.join(2)
    assert result["ready"] is ready


@pytest.mark.parametrize("response", [
    b"RTSP/1.0 404 Not Found\r\n\r\n",
    b"RTSP/1.0 200 OK\r\nContent-Length: 100\r\n\r\nm=video ",
    b"RTSP/1.0 200 OK\r\nContent-Length: 1000000\r\n\r\n",
    b"RTSP/1.0 200 OK\r\nContent-Length: invalid\r\n\r\n",
    b"invalid\r\n\r\n",
])
def test_rtsp_fails_closed_on_unavailable_or_invalid_stream(response):
    port, thread = serve(response)
    assert probe("127.0.0.1", port, "live")["ready"] is False
    thread.join(2)


def test_readiness_state_must_be_fresh_and_successful(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.probe_rtsp.time.time", lambda: 100)
    state = tmp_path / "state.json"
    assert not state_ready(state, 30)
    for timestamp, ready, expected in [(99, True, True), (69, True, False),
                                       (101, True, False), (99, False, False)]:
        state.write_text(json.dumps({"checked_at": timestamp, "ready": ready}))
        assert state_ready(state, 30) is expected


def test_inventory_excludes_environment_and_raw_logs(monkeypatch):
    item = {"Name": "/selected", "Config": {"Image": "postgres:16", "Env": ["PASSWORD=secret"],
            "Labels": {"com.docker.compose.project": "securepulse", "com.docker.compose.service": "postgres"}},
            "State": {"Status": "running", "Health": {"Status": "unhealthy", "Log": ["secret"]}},
            "HostConfig": {"PortBindings": {"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5432"}]}},
            "Mounts": [{"Type": "volume", "Name": "securepulse_postgres_data", "Destination": "/data"}]}
    monkeypatch.setattr(operations, "command", lambda args: "container-id" if args[1] == "ps" else json.dumps([item]))
    records = operations.inventory()
    assert "secret" not in json.dumps(records)
    assert records[0]["all_interface_ports"] == ["5432/tcp"]
    assert records[0]["mounts"][0]["Name"] == "securepulse_postgres_data"


def test_recovery_refuses_restart_without_healthy_camera_baseline(monkeypatch):
    monkeypatch.setattr(operations, "healthy", lambda *args: False)
    monkeypatch.setattr(operations, "command", lambda *args, **kwargs: pytest.fail("must not restart"))
    result, passed = operations.recover(SimpleNamespace(backend="http://localhost", cameras="front_door,laptop_camera"))
    assert not passed
    assert result["reason"] == "healthy_baseline_required"


@pytest.mark.parametrize("actual_project,expected_pass", [("chosen-project", True), ("other-project", False)])
def test_recovery_only_restarts_the_verified_project_service(monkeypatch, actual_project, expected_pass):
    commands = []
    labels = {"com.docker.compose.project": actual_project, "com.docker.compose.service": "mqtt"}

    def run(arguments, **kwargs):
        commands.append(arguments)
        if arguments[1] == "inspect":
            return json.dumps([{"Config": {"Labels": labels}}])
        if "ps" in arguments:
            return "one-container"
        return ""

    monkeypatch.setattr(operations, "healthy", lambda *args: True)
    monkeypatch.setattr(operations, "command", run)
    monkeypatch.setattr(operations.time, "sleep", lambda *args: None)
    monkeypatch.setattr(operations, "edge_sample", lambda *args: {
        "queue_rejections": 0, "processing_failures": 0, "invalid_event_count": 0, "adapter_delivery_failures": 0})
    args = SimpleNamespace(backend="http://localhost", cameras="front_door,laptop_camera",
                           project="chosen-project", env_file="ignored.env", restart_service="mqtt", duration=1, interval=0.001)
    result, passed = operations.recover(args)
    assert passed is expected_pass
    restarts = [arguments for arguments in commands if "restart" in arguments]
    assert len(restarts) == (1 if expected_pass else 0)
    if expected_pass:
        assert restarts[0][-2:] == ["restart", "mqtt"]
        assert "chosen-project" in restarts[0]
    else:
        assert result["reason"] == "target_identity_mismatch"


@pytest.mark.parametrize("output,black,passed", [("", False, False),
                                                ("out_time_us=8000000", True, False),
                                                ("out_time_us=8000000", False, True)])
def test_source_check_requires_decoded_frames_without_black_intervals(monkeypatch, output, black, passed):
    monkeypatch.setattr(operations, "probe", lambda *args: {"path": "live", "ready": True})
    monkeypatch.setattr(operations.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout=output, stderr="black_start:0" if black else ""))
    result, actual = operations.source_check(SimpleNamespace(paths="live", rtsp_host="127.0.0.1", rtsp_port=18554))
    assert actual is passed
    assert result["status"] == ("pass" if passed else "fail")
