"""Boundary checks for file serving and secret-safe logging."""

import logging
from types import SimpleNamespace

import pytest

from app.api.evidence import media_path
from app.core.exceptions import ApplicationError
from app.core.logging import RedactingFormatter
from app.core.logging import configure_logging


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


def test_nonpropagating_uvicorn_access_logs_redact_query_tokens():
    """Uvicorn's own access handler must not bypass application redaction."""
    import io
    stream = io.StringIO()
    logger = logging.getLogger("uvicorn.access")
    saved = logger.handlers[:], logger.propagate, logger.level, logger.disabled
    root_handlers = logging.getLogger().handlers[:]
    root_level = logging.getLogger().level
    try:
        logger.handlers = [logging.StreamHandler(stream)]
        logger.propagate = False
        # Alembic's logging configuration may disable existing named loggers.
        logger.disabled = False
        logger.setLevel(logging.INFO)
        configure_logging("INFO")
        logger.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1", "GET", "/content?grant=eyJabc.def.ghi", "1.1", 200)
        assert "[REDACTED_TOKEN]" in stream.getvalue()
        assert "eyJabc" not in stream.getvalue()
    finally:
        logger.handlers, logger.propagate, logger.level, logger.disabled = saved
        logging.getLogger().handlers = root_handlers
        logging.getLogger().setLevel(root_level)
