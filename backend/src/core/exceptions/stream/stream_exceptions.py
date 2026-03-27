from __future__ import annotations

from src.core.exceptions.base.app_exception import AppException


class StreamAlreadyRunningException(AppException):
    """Raise when a caller tries to start an already-running stream."""

    def __init__(self, camera_id: str) -> None:
        """Create a conflict exception for duplicate stream starts."""

        super().__init__(
            message=f"Stream for camera '{camera_id}' is already running.",
            error_code="STREAM_ALREADY_RUNNING",
            status_code=409,
        )


class StreamNotRunningException(AppException):
    """Raise when a caller tries to stop a stream that is not active."""

    def __init__(self, camera_id: str) -> None:
        """Create a conflict exception for stopping an inactive stream."""

        super().__init__(
            message=f"Stream for camera '{camera_id}' is not running.",
            error_code="STREAM_NOT_RUNNING",
            status_code=409,
        )


class StreamWorkerStartException(AppException):
    """Raise when the backend cannot create the stream worker process."""

    def __init__(self, camera_id: str, details: dict[str, object] | None = None) -> None:
        """Create an error describing a worker boot failure."""

        super().__init__(
            message=f"Worker process for camera '{camera_id}' could not be started.",
            error_code="STREAM_WORKER_START_FAILED",
            status_code=500,
            details=details,
        )


class MediaMtxUnavailableException(AppException):
    """Raise when MediaMTX is not reachable for stream startup."""

    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """Create a service-unavailable error for MediaMTX connection failures."""

        super().__init__(
            message=(
                f"MediaMTX is not reachable for camera '{camera_id}'. "
                "Start MediaMTX or correct the configured RTSP base URL."
            ),
            error_code="MEDIAMTX_UNAVAILABLE",
            status_code=503,
            details={"rtsp_url": rtsp_url, **(details or {})},
        )


class MediaMtxStartupException(AppException):
    """Raise when the backend cannot start or prepare MediaMTX."""

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        """Create a startup failure for the managed MediaMTX service."""

        super().__init__(
            message=message,
            error_code="MEDIAMTX_START_FAILED",
            status_code=503,
            details=details,
        )
