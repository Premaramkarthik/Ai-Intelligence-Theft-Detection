from __future__ import annotations

from urllib.parse import urljoin, urlparse, urlunparse

from src.core.config import Settings
from src.models.camera import CameraRecord, StreamProtocol, StreamRecord, StreamStatus
from src.schemas.stream_responses import (
    StreamFallbackInfo,
    StreamInfoResponse,
    WorkerStateResponse,
)
from src.services.stream.stream_manager import WorkerSnapshot


class StreamContractService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build_contract(
        self,
        camera: CameraRecord,
        stream_record: StreamRecord | None,
        worker_snapshot: WorkerSnapshot,
    ) -> StreamInfoResponse:
        relative_playback_url = self._relative_playback_url(camera.id)
        playback_url = (
            self._absolute_http_url(stream_record.playback_path)
            if stream_record and stream_record.playback_path
            else self._absolute_http_url(relative_playback_url)
        )

        if stream_record is None:
            status = StreamStatus.stopped
            protocol = StreamProtocol.hls
            stream_id = f"stream_{camera.id}"
            last_error_code = None
            last_error_message = None
            updated_at = None
            last_event_at = None
            started_at = None
        else:
            status = stream_record.status
            protocol = stream_record.protocol
            stream_id = stream_record.stream_id
            last_error_code = stream_record.last_error_code
            last_error_message = stream_record.last_error_message
            updated_at = stream_record.updated_at
            last_event_at = stream_record.last_event_at
            started_at = stream_record.worker_started_at

        return StreamInfoResponse(
            camera_id=camera.id,
            camera_name=camera.name,
            stream_id=stream_id,
            stream_identifier=f"{camera.id}:{stream_id}",
            status=status,
            protocol=protocol,
            playback_url=playback_url,
            relative_playback_url=relative_playback_url,
            websocket_url=self._websocket_public_url(),
            fallback=self._build_fallback(status),
            started_at=started_at,
            updated_at=updated_at,
            last_event_at=last_event_at,
            last_error_code=last_error_code,
            last_error_message=last_error_message,
            worker=WorkerStateResponse(
                desired_state=worker_snapshot.desired_state,
                is_registered=worker_snapshot.is_registered,
                is_process_alive=worker_snapshot.is_process_alive,
                process_id=worker_snapshot.process_id,
                restart_count=worker_snapshot.restart_count,
                reconnect_attempts=worker_snapshot.reconnect_attempts,
            ),
        )

    def _build_fallback(self, status: StreamStatus) -> StreamFallbackInfo | None:
        if status == StreamStatus.running:
            return None
        if status == StreamStatus.starting:
            return StreamFallbackInfo(
                kind="warming_up",
                message=(
                    "HLS playlist is being prepared. "
                    "Subscribe to WebSocket updates and retry shortly."
                ),
                retry_after_seconds=2,
            )
        if status in {StreamStatus.reconnecting, StreamStatus.error, StreamStatus.crashed}:
            return StreamFallbackInfo(
                kind="retry",
                message=(
                    "The worker is reconnecting to the camera. "
                    "Keep the WebSocket open for status updates."
                ),
                retry_after_seconds=3,
            )
        return StreamFallbackInfo(
            kind="start_required",
            message="Stream is not active yet. Call the start endpoint before opening the player.",
            retry_after_seconds=None,
        )

    def _relative_playback_url(self, camera_id: str) -> str:
        return (
            f"{self._settings.media_mount_path}/"
            f"{self._settings.hls_directory_name}/{camera_id}/index.m3u8"
        )

    def _absolute_http_url(self, relative_path: str) -> str:
        return urljoin(
            f"{self._settings.public_api_base_url.rstrip('/')}/",
            relative_path.lstrip("/"),
        )

    def _websocket_public_url(self) -> str:
        if self._settings.public_ws_base_url:
            return f"{self._settings.public_ws_base_url.rstrip('/')}/streams/ws/updates"

        parsed = urlparse(self._settings.public_api_base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        websocket_base = urlunparse(
            parsed._replace(scheme=scheme, path="", params="", query="", fragment="")
        )
        return f"{websocket_base.rstrip('/')}/streams/ws/updates"
