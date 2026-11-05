"""Application exception handling."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

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
            headers={**exception.headers, **({"Cache-Control": "no-store"} if request.url.path.startswith("/api/v1/dashboard") else {})},
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
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exception: RequestValidationError) -> JSONResponse:
        # Validation errors must not echo submitted passwords or other input.
        return JSONResponse(status_code=422, headers={"Cache-Control": "no-store"}, content={
            "detail": [{"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
                       for item in exception.errors()]
        })
