"""Application logging configuration."""

import logging


def configure_logging(level: str) -> None:
    """Configure consistent application logs without exposing configuration secrets."""

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )