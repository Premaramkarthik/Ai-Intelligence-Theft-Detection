from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.core.exceptions.base.app_exception import AppException
from src.utils.response import build_error_payload


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(_: Request, exc: AppException) -> JSONResponse:
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
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=build_error_payload(
                message="An unexpected server error occurred.",
                error_code="INTERNAL_SERVER_ERROR",
                meta={"exception": exc.__class__.__name__},
            ),
        )
