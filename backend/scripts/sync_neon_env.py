"""Copy Neon-managed server variables into existing private runtime env files.

Run from the repository root after neon deploy/env pull. Existing unrelated
settings are preserved, and each changed file gets a private recovery copy.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import re

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[2]
KEYS = ("DATABASE_URL", "DATABASE_URL_UNPOOLED", "NEON_AUTH_BASE_URL", "NEON_AUTH_JWKS_URL", "NEON_BRANCH")
STORAGE_KEYS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ENDPOINT_URL_S3", "AWS_REGION")


def sync(source):
    values = dict(dotenv_values(source, interpolate=False))
    missing = [key for key in KEYS if not values.get(key)]
    if missing:
        raise ValueError("Missing Neon-managed variables: " + ", ".join(missing))
    from urllib.parse import urlsplit
    if not (urlsplit(values["DATABASE_URL"]).hostname or "").endswith(".neon.tech"):
        raise ValueError("Refusing to use a database URL that is not a Neon endpoint")
    # Media stays on the host. Neon only holds identity and application metadata.
    values.update(EVIDENCE_STORAGE="local", EVIDENCE_BUCKET="assets", AUTH_ENABLED="true")
    values.update({key: "" for key in STORAGE_KEYS})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for relative in ("backend/.env", "backend/deployment/.env"):
        path = ROOT / relative
        if not path.is_file():
            raise ValueError(f"Missing existing private runtime configuration: {relative}")
    for relative in ("backend/.env", "backend/deployment/.env"):
        path = ROOT / relative
        original = path.read_text()
        content = original
        for key in (*KEYS, *STORAGE_KEYS, "EVIDENCE_STORAGE", "EVIDENCE_BUCKET", "AUTH_ENABLED"):
            value = values[key]
            if "\n" in value or "\r" in value:
                raise ValueError(f"Invalid multi-line environment value: {key}")
            line = key + "='" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
            pattern = rf"^{re.escape(key)}=.*$"
            if re.search(pattern, content, flags=re.MULTILINE):
                content = re.sub(pattern, lambda match: line, content, flags=re.MULTILINE)
            else:
                content = content.rstrip() + "\n" + line + "\n"
        if content != original:
            backup = path.with_name(path.name + ".pre-neon-" + stamp)
            backup.write_text(original)
            backup.chmod(0o600)
            path.write_text(content)
            print(f"Updated {relative}; previous configuration preserved privately.")
        else:
            print(f"Already synchronized: {relative}")
        path.chmod(0o600)
    source.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / ".env.local")
    args = parser.parse_args()
    try:
        sync(args.source.resolve())
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print("No database migrations or services were started; no secrets were printed.")


if __name__ == "__main__":
    main()
