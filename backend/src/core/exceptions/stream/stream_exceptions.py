from __future__ import annotations

from src.core.exceptions.base.app_exception import AppException


class StreamAlreadyRunningException(AppException):
    def __init__(self, camera_id: str) -> None:
        super().__init__(
            message=f"Stream for camera '{camera_id}' is already running.",
            error_code="STREAM_ALREADY_RUNNING",
            status_code=409,
        )


class StreamNotRunningException(AppException):
    def __init__(self, camera_id: str) -> None:
        super().__init__(
            message=f"Stream for camera '{camera_id}' is not running.",
            error_code="STREAM_NOT_RUNNING",
            status_code=409,
        )


class StreamWorkerStartException(AppException):
    def __init__(self, camera_id: str, details: dict[str, object] | None = None) -> None:
        super().__init__(
            message=f"Worker process for camera '{camera_id}' could not be started.",
            error_code="STREAM_WORKER_START_FAILED",
            status_code=500,
            details=details,
        )
