"""Application exception handling."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApplicationError(Exception):
    """Safe, client-facing application error."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.headers = headers or {}


def register_exception_handlers(app: FastAPI) -> None:
    """Register safe error responses for unexpected application failures."""

    @app.exception_handler(ApplicationError)
    async def application_error_handler(
        request: Request, exception: ApplicationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exception.status_code,
            headers=exception.headers,
            content={"error": {"code": exception.code, "message": exception.message}},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exception: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled application error", extra={"path": request.url.path})
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred.",
                }
            },
        )