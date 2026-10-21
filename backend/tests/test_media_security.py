"""Boundary checks for file serving and secret-safe logging."""

import logging
from types import SimpleNamespace

import pytest

from app.api.evidence import media_path
from app.core.exceptions import ApplicationError
from app.core.logging import RedactingFormatter


def test_media_root_rejects_escape_missing_files_and_active_content(tmp_path, monkeypatch):
    root = tmp_path / "media"
    root.mkdir()
    (tmp_path / "private.jpg").write_bytes(b"private")
    (root / "active.html").write_text("<script>bad()</script>")
    monkeypatch.setattr("app.api.evidence.get_settings", lambda: SimpleNamespace(evidence_root=str(root)))
    for reference in ("../private.jpg", str(tmp_path / "private.jpg"), "missing.jpg", "active.html"):
        with pytest.raises(ApplicationError) as error:
            media_path(reference)
        assert error.value.status_code == 404


def test_connection_strings_and_jwts_are_redacted():
    message = "Failed postgresql://user:password@host/db token eyJabc.def.ghi rtsp://user:pass@camera/live"
    record = logging.LogRecord("test", logging.ERROR, "", 0, message, (), None)
    rendered = RedactingFormatter("%(message)s").format(record)
    assert "password" not in rendered and "eyJabc" not in rendered and "user:pass" not in rendered
