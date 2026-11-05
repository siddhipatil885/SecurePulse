"""Bounded, dependency-free RTSP video readiness probe (no images retained)."""

import argparse
import json
import os
from pathlib import Path
import re
import socket
import time


def probe(host: str, port: int, path: str, timeout: float = 3) -> dict:
    """Require a successful DESCRIBE and video SDP, not just an open TCP port."""
    if not re.fullmatch(r"[a-zA-Z0-9_/-]+", path):
        raise ValueError("Use an RTSP path without credentials, whitespace, or query parameters")
    deadline = time.monotonic() + timeout
    try:
        with socket.create_connection((host, port), timeout=timeout) as connection:
            connection.sendall(
                (f"DESCRIBE rtsp://{host}:{port}/{path} RTSP/1.0\r\n"
                 "CSeq: 1\r\nAccept: application/sdp\r\n\r\n").encode("ascii")
            )
            received = b""
            while b"\r\n\r\n" not in received:
                if time.monotonic() >= deadline:
                    raise TimeoutError
                connection.settimeout(max(0.001, deadline - time.monotonic()))
                chunk = connection.recv(4096)
                if not chunk or len(received) + len(chunk) > 65536:
                    return {"path": path, "ready": False, "reason": "invalid_response"}
                received += chunk
            headers, body = received.split(b"\r\n\r\n", 1)
            if headers.split(b"\r\n", 1)[0].split()[1:2] != [b"200"]:
                return {"path": path, "ready": False, "reason": "stream_unavailable"}
            fields = {}
            for line in headers.split(b"\r\n")[1:]:
                key, _, value = line.partition(b":")
                fields[key.lower()] = value.strip()
            length = int(fields.get(b"content-length", b"0"))
            if not 0 < length <= 65536:
                return {"path": path, "ready": False, "reason": "invalid_sdp_length"}
            while len(body) < length:
                if time.monotonic() >= deadline:
                    raise TimeoutError
                connection.settimeout(max(0.001, deadline - time.monotonic()))
                chunk = connection.recv(min(4096, length - len(body)))
                if not chunk:
                    return {"path": path, "ready": False, "reason": "truncated_sdp"}
                body += chunk
            ready = any(line.startswith(b"m=video ") for line in body[:length].splitlines())
            return {"path": path, "ready": ready, "reason": "video_sdp" if ready else "no_video"}
    except (OSError, ValueError, IndexError, UnicodeError) as error:
        return {"path": path, "ready": False, "reason": type(error).__name__}


def state_ready(path: Path, max_age: float) -> bool:
    try:
        state = json.loads(path.read_text())
        age = time.time() - state["checked_at"]
        return state["ready"] is True and 0 <= age <= max_age
    except (OSError, ValueError, KeyError, TypeError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8554)
    parser.add_argument("--paths", default="live,webcam")
    parser.add_argument("--timeout", type=float, default=3)
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--state", type=Path, default=Path("/tmp/rtsp-ready.json"))
    parser.add_argument("--check-state", action="store_true")
    parser.add_argument("--max-age", type=float, default=30)
    args = parser.parse_args()
    if args.check_state:
        return 0 if state_ready(args.state, args.max_age) else 1
    paths = [path.strip(" /") for path in args.paths.split(",") if path.strip(" /")]
    if not paths or len(paths) > 8 or args.timeout <= 0 or args.interval <= 0:
        parser.error("Specify 1–8 paths and positive timeout/interval")
    while True:
        checks = [probe(args.host, args.port, path, args.timeout) for path in paths]
        result = {"checked_at": time.time(), "ready": all(item["ready"] for item in checks), "streams": checks}
        print(json.dumps(result), flush=True)
        if not args.watch:
            return 0 if result["ready"] else 1
        temporary = args.state.with_suffix(".tmp")
        temporary.write_text(json.dumps(result))
        os.replace(temporary, args.state)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
