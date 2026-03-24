from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from src.schemas.common import ApiResponse, ApiStatus


def build_success_payload(
    message: str,
    data: Any = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    envelope = ApiResponse[Any](
        status=ApiStatus.success,
        message=message,
        data=data,
        meta=meta,
    )
    return jsonable_encoder(envelope)


def build_error_payload(
    message: str,
    error_code: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    envelope = ApiResponse[Any](
        status=ApiStatus.error,
        message=message,
        data=None,
        error_code=error_code,
        meta=meta,
    )
    return jsonable_encoder(envelope)


def success_response(
    message: str,
    data: Any = None,
    meta: dict[str, Any] | None = None,
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=build_success_payload(message=message, data=data, meta=meta),
    )
