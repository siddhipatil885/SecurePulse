"""Configure phone access on the machine running the SecurePulse backend.

Run on the actual host, not on a machine merely preparing its source files.
Only public client addresses and the authenticated backend bind are changed.
"""
import argparse
import ipaddress
from pathlib import Path
import re
import socket
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]


def lan_address():
    # A UDP connect selects an outbound interface without transmitting a packet.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.connect(("192.0.2.1", 80))
        address = connection.getsockname()[0]
    parsed = ipaddress.ip_address(address)
    if not parsed.is_private or parsed.is_loopback or parsed.is_link_local:
        raise ValueError("No private LAN interface found. Use --host with the host's LAN IP.")
    return address


def read_value(path, key, default=""):
    for line in path.read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip("\"'")
    return default


def update(path, values):
    if not path.is_file():
        raise ValueError(f"Missing configuration: {path.relative_to(ROOT)}")
    content = path.read_text()
    for key, value in values.items():
        line = f"{key}={value}"
        pattern = rf"^{re.escape(key)}=.*$"
        if re.search(pattern, content, flags=re.MULTILINE):
            content = re.sub(pattern, lambda match: line, content, flags=re.MULTILINE)
        else:
            content = content.rstrip() + "\n" + line + "\n"
    path.write_text(content)
    path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    address_group = parser.add_mutually_exclusive_group()
    address_group.add_argument("--host", help="Override automatic LAN IP detection (for example when using a VPN).")
    address_group.add_argument("--url", help="Existing HTTPS API origin, without /api/v1. Does not open a LAN bind.")
    args = parser.parse_args()
    deployment = ROOT / "backend/deployment/.env"
    backend = ROOT / "backend/.env"
    mobile = ROOT / "mobile/reporter-app/.env"
    dashboard = ROOT / "backend/dashboard/.env.local"
    for path in (deployment, backend, mobile, dashboard):
        if not path.is_file():
            parser.error(f"Missing configuration: {path.relative_to(ROOT)}")
    try:
        if args.url:
            parsed = urlsplit(args.url)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                    or parsed.query or parsed.fragment or parsed.path.rstrip("/")):
                raise ValueError("Use an HTTPS origin without credentials, path, query or /api/v1.")
            url = args.url.rstrip("/")
        else:
            address = ipaddress.ip_address(args.host or lan_address())
            if address.version != 4 or not address.is_private or address.is_loopback or address.is_link_local:
                raise ValueError("Use a private LAN IPv4 address.")
            port = int(read_value(deployment, "BACKEND_PORT", "18000"))
            if not 1 <= port <= 65535:
                raise ValueError("Invalid BACKEND_PORT.")
            for path in (deployment, backend):
                if read_value(path, "AUTH_ENABLED").lower() != "true" or len(read_value(path, "JWT_SECRET")) < 32:
                    raise ValueError("Enable backend authentication and a signing secret before LAN access.")
            url = f"http://{address}:{port}"
            update(deployment, {"BACKEND_BIND_ADDRESS": str(address)})
            update(backend, {"HOST": str(address), "PORT": str(port)})
            update(dashboard, {"VITE_BACKEND_URL": url})
        update(mobile, {"EXPO_PUBLIC_SERVER_URL": url})
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Mobile API configured: {url}")
    print("Restart the backend/container and Metro. The phone must reach this host on the same LAN.")
    if not args.url:
        print(f"For a direct Python backend: uvicorn app.main:app --host {address} --port {port} (from backend/)")
    print("Restart Vite after updating its backend proxy address.")
    print("Use HTTPS for deployed native builds. This command does not change firewall rules.")


if __name__ == "__main__":
    main()
