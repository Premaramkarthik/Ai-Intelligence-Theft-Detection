from __future__ import annotations

from src.core.exceptions.base.app_exception import AppException


class CameraNotFoundException(AppException):
    def __init__(self, camera_id: str) -> None:
        super().__init__(
            message=f"Camera '{camera_id}' was not found.",
            error_code="CAMERA_NOT_FOUND",
            status_code=404,
        )


class CameraValidationException(AppException):
    def __init__(self, message: str, error_code: str = "CAMERA_VALIDATION_FAILED") -> None:
        super().__init__(message=message, error_code=error_code, status_code=400)


class CameraSourceUnavailableException(AppException):
    def __init__(
        self,
        camera_id: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(
            message=(
                f"Camera '{camera_id}' RTSP source is unavailable. "
                f"{message}"
            ),
            error_code="CAMERA_SOURCE_UNAVAILABLE",
            status_code=503,
            details={"camera_id": camera_id, **(details or {})},
        )


class CameraConflictException(AppException):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, error_code="CAMERA_CONFLICT", status_code=409)
