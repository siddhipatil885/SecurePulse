"""Application logging configuration."""

import logging
import re


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        rendered = super().format(record)
        rendered = re.sub(r"(?i)(postgres(?:ql)?(?:\+[a-z0-9]+)?|rtsps?)://[^\s]+", "[REDACTED_CONNECTION]", rendered)
        rendered = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED_TOKEN]", rendered)
        return rendered


def configure_logging(level: str) -> None:
    """Configure consistent application logs without exposing configuration secrets."""

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
