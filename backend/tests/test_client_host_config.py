"""Host discovery config tests use temporary files, never actual credentials."""
import importlib.util
from pathlib import Path
import sys

import pytest


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = Path(__file__).parents[1] / "scripts/configure_client_host.py"
    spec = importlib.util.spec_from_file_location("client_host_config", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = tmp_path
    for name, text in {
        "backend/deployment/.env": "AUTH_ENABLED=true\nJWT_SECRET=test-only-secret-of-at-least-32-characters\nBACKEND_PORT=18000\nBACKEND_BIND_ADDRESS=127.0.0.1\nPOSTGRES_PASSWORD=retain-this-value\n",
        "backend/.env": "AUTH_ENABLED=true\nJWT_SECRET=test-only-secret-of-at-least-32-characters\nHOST=127.0.0.1\nPORT=18000\nDATABASE_URL=retain-this-URL\n",
        "backend/dashboard/.env.local": "VITE_BACKEND_URL=http://127.0.0.1:18000\nVITE_API_BASE_URL=/api/v1\n",
        "mobile/reporter-app/.env": "EXPO_PUBLIC_SERVER_URL=\nEXPO_PUBLIC_EXPO_PROJECT_ID=retain-project-id\n",
    }.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    monkeypatch.setattr(sys, "argv", [str(path)])
    return module


def test_lan_discovery_keeps_clients_consistent_and_preserves_credentials(config, monkeypatch):
    monkeypatch.setattr(config, "lan_address", lambda: "192.168.1.42")
    config.main()
    root = config.ROOT
    assert "BACKEND_BIND_ADDRESS=192.168.1.42" in (root / "backend/deployment/.env").read_text()
    assert "POSTGRES_PASSWORD=retain-this-value" in (root / "backend/deployment/.env").read_text()
    assert "DATABASE_URL=retain-this-URL" in (root / "backend/.env").read_text()
    assert "VITE_BACKEND_URL=http://192.168.1.42:18000" in (root / "backend/dashboard/.env.local").read_text()
    assert "EXPO_PUBLIC_SERVER_URL=http://192.168.1.42:18000" in (root / "mobile/reporter-app/.env").read_text()
    assert "EXPO_PUBLIC_EXPO_PROJECT_ID=retain-project-id" in (root / "mobile/reporter-app/.env").read_text()


def test_anonymous_backend_is_not_opened_to_lan(config, monkeypatch):
    target = config.ROOT / "backend/.env"
    target.write_text(target.read_text().replace("AUTH_ENABLED=true", "AUTH_ENABLED=false"))
    before = {p: p.read_text() for p in config.ROOT.rglob(".env*")}
    monkeypatch.setattr(config, "lan_address", lambda: "192.168.1.42")
    with pytest.raises(SystemExit):
        config.main()
    assert all(p.read_text() == text for p, text in before.items())


def test_https_origin_configures_mobile_without_changing_host_bind(config, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["configure_client_host.py", "--url", "https://api.example.test"])
    before = (config.ROOT / "backend/deployment/.env").read_text()
    config.main()
    assert (config.ROOT / "backend/deployment/.env").read_text() == before
    assert "EXPO_PUBLIC_SERVER_URL=https://api.example.test" in (config.ROOT / "mobile/reporter-app/.env").read_text()
