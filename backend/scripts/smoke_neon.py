"""Opt-in live Neon acceptance through a started SecurePulse API.

Creates a clearly identified test account/property/report on the selected Neon
branch and retains them as verification evidence. Never prints credentials.
"""
import argparse
import base64
from pathlib import Path
import os
import secrets
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-source", type=Path, default=ROOT / ".env.local")
    parser.add_argument("--port", type=int, default=18083)
    args = parser.parse_args()
    env = dict(dotenv_values(ROOT / "backend/.env", interpolate=False))
    env.update(dotenv_values(args.env_source, interpolate=False))
    for key in ("DATABASE_URL", "DATABASE_URL_UNPOOLED", "NEON_AUTH_BASE_URL"):
        if not env.get(key):
            parser.error(f"Missing Neon variable: {key}")
    env.update(AUTH_ENABLED="true", EVIDENCE_STORAGE="local", APP_ENV="development")
    media_root = Path(env.get("EVIDENCE_ROOT") or "./operational-evidence/media")
    if not media_root.is_absolute():
        media_root = ROOT / "backend" / media_root
    media_root = media_root.resolve()
    media_root.mkdir(parents=True, exist_ok=True)
    env["EVIDENCE_ROOT"] = str(media_root)
    url = f"http://127.0.0.1:{args.port}"
    marker = uuid4().hex
    email = f"securepulse-smoke-{marker}@example.invalid"
    password = secrets.token_urlsafe(24) + "1a"
    replacement = secrets.token_urlsafe(24) + "2b"
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    engine = create_engine(make_url(env["DATABASE_URL_UNPOOLED"]).set(drivername="postgresql+psycopg2"),
                           connect_args={"connect_timeout": 20})
    process = None
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0017_reporter_active_assignment"
        print("PASS Neon Postgres: SELECT 1 and migration 0017", flush=True)
        with tempfile.TemporaryFile(mode="w+t") as log:
            process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                "--port", str(args.port), "--log-level", "warning"], cwd=ROOT / "backend",
                env={**os.environ, **{k: v for k, v in env.items() if v is not None}}, stdout=log, stderr=log)
            with httpx.Client(base_url=url, timeout=60, follow_redirects=False) as client:
                for attempt in range(150):
                    if process.poll() is not None:
                        raise RuntimeError("Backend exited during startup; private log omitted")
                    try:
                        if client.get("/health", timeout=1).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.2)
                else:
                    raise RuntimeError("Backend startup timed out")
                print("PASS application started: GET /health -> 200", flush=True)
                browser = {"X-Dashboard-Request": "1"}
                def check(response, status):
                    if response.status_code != status:
                        try:
                            code = response.json().get("error", {}).get("code", "unknown")
                        except ValueError:
                            code = "non-JSON response"
                        raise RuntimeError(f"{response.request.method} {response.request.url.path}: expected {status}, got {response.status_code} ({code})")
                    return response
                signup = check(client.post("/api/v1/dashboard/auth/register", headers=browser, json={
                    "full_name": "Neon verification account", "email": email, "password": password,
                    "name": "Neon verification property", "address": "Integration test location"}), 201).json()
                property_id = signup["properties"][0]["id"]
                check(client.get("/api/v1/dashboard/auth/session"), 200)
                check(client.post("/api/v1/dashboard/auth/logout", headers=browser), 204)
                check(client.get("/api/v1/dashboard/auth/session"), 401)
                check(client.post("/api/v1/dashboard/auth/login", headers=browser,
                    json={"email": email, "password": password}), 200)
                print("PASS Neon Auth: signup, session restoration, logout denial and dashboard sign-in", flush=True)
                token = check(client.post("/api/v1/auth/login", json={"email": email, "password": password}), 200).json()["access_token"]
                auth = {"Authorization": "Bearer " + token}
                check(client.get("/api/v1/auth/me", headers=auth), 200)
                report = check(client.post("/api/v1/reporter/incidents", headers={**auth, "X-Idempotency-Key": marker},
                    json={"property_id": property_id, "incident_type": "THEFT", "address": "Integration test location"}), 201).json()
                history = check(client.get('/api/v1/reporter/incidents?include_details=false', headers=auth), 200).json()
                assert any(item['id'] == report['id'] and item['details_included'] is False for item in history['items'])
                image = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
                upload_path = f"/api/v1/reporter/incidents/{report['id']}/evidence"
                for attempt in range(2):
                    uploaded = check(client.post(upload_path, headers={**auth, "X-Idempotency-Key": "upload-" + marker},
                        files={"file": ("neon-verification.png", image, "image/png")}), 200).json()
                    assert len(uploaded["evidence"]) == 1
                evidence_id = uploaded["evidence"][0]["id"]
                grant = check(client.post(upload_path + f"/{evidence_id}/access", headers=auth), 200).json()
                check(client.get(grant["url"]), 401)
                assert check(client.get(grant["url"], headers=auth), 200).content == image
                partial = check(client.get(grant["url"], headers={**auth, "Range": "bytes=0-7"}), 206)
                assert partial.content == image[:8]
                operator = f"/api/v1/dashboard/properties/{property_id}/cases/reporter/{report['id']}"
                check(client.get(operator), 200)
                grant = check(client.post(operator + f"/evidence/{evidence_id}/access", headers=browser), 200).json()
                assert check(client.get(grant["url"]), 200).content == image
                with engine.connect() as connection:
                    user = connection.execute(text("SELECT subject, password_hash FROM users WHERE id=:id"), {"id": signup["id"]}).one()
                    assert user.subject.startswith("neon:") and user.password_hash is None
                    reference = connection.scalar(text("SELECT file_path FROM reporter_incident_evidence WHERE id=:id"), {"id": evidence_id})
                    assert not reference.startswith("s3://")
                    assert (media_root / reference).read_bytes() == image
                print("PASS local media: bytes stay on disk, only metadata in Neon; upload retry, authenticated reporter/operator downloads and Range 206", flush=True)
                check(client.post("/api/v1/auth/password", headers=auth,
                    json={"current_password": password, "new_password": replacement}), 204)
                check(client.get("/api/v1/auth/me", headers=auth), 401)
                check(client.post("/api/v1/auth/login", json={"email": email, "password": password}), 401)
                new_token = check(client.post("/api/v1/auth/login", json={"email": email, "password": replacement}), 200).json()["access_token"]
                check(client.post("/api/v1/auth/logout", headers={"Authorization": "Bearer " + new_token}), 204)
                check(client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + new_token}), 401)
                print("PASS Neon password change and application session revocation", flush=True)
                ready = client.get("/health/ready").json()
                print("Dependency readiness:", ready.get("checks", {}), flush=True)
                print(f"Retained verification records: user #{signup['id']}, property #{property_id}, report #{report['id']} (example.invalid account)", flush=True)
                print("PASS Neon Postgres + Auth and local media through the running SecurePulse API", flush=True)
    except Exception as error:
        # Exception text from SDKs can contain service URLs and credentials.
        if isinstance(error, RuntimeError):
            print("FAIL " + str(error), file=sys.stderr)
        else:
            print("FAIL " + type(error).__name__ + "; details omitted to protect credentials", file=sys.stderr)
        return 1
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
