from __future__ import annotations

import traceback
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.core.exceptions.base.app_exception import AppException
from src.core.logger.logger import get_logger
from src.utils.response import build_error_payload

LOGGER = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(_: Request, exc: AppException) -> JSONResponse:
        _log_error_location(exc)
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(
                message=exc.message,
                error_code=exc.error_code,
                meta=exc.details or None,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        _log_error_location(exc)
        details: dict[str, Any] = {"validation_errors": exc.errors()}
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=build_error_payload(
                message="Request validation failed.",
                error_code="REQUEST_VALIDATION_ERROR",
                meta=details,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        _log_error_location(exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=build_error_payload(
                message="An unexpected server error occurred.",
                error_code="INTERNAL_SERVER_ERROR",
                meta={"exception": exc.__class__.__name__},
            ),
        )


def _log_error_location(exc: Exception) -> None:
    """Log only the failing function, line number, and error message for an exception."""

    summary = _build_error_summary(exc)
    LOGGER.error("%s", summary)


def _build_error_summary(exc: Exception) -> str:
    """Build a concise error summary with function name and line number."""

    extracted_frames = traceback.extract_tb(exc.__traceback__)
    if not extracted_frames:
        return f"{exc.__class__.__name__}: {exc}"
    frame = extracted_frames[-1]
    return f"{frame.name}:{frame.lineno} | {exc.__class__.__name__}: {exc}"
