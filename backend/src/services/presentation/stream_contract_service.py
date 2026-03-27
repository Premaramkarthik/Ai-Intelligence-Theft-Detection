from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from src.core.config import Settings
from src.models.camera import CameraRecord, StreamProtocol, StreamRecord, StreamStatus
from src.schemas.stream_responses import (
    StreamAccessUrls,
    StreamFallbackInfo,
    StreamInfoResponse,
    WorkerStateResponse,
)
from src.services.realtime_video.contracts import MediaMtxStreamEndpoints
from src.services.realtime_video.stream_manager import WorkerSnapshot


class StreamContractService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build_contract(
        self,
        camera: CameraRecord,
        stream_record: StreamRecord | None,
        worker_snapshot: WorkerSnapshot,
        stream_endpoints: MediaMtxStreamEndpoints,
    ) -> StreamInfoResponse:
        if stream_record is None:
            status = StreamStatus.stopped
            protocol = StreamProtocol.webrtc
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

        playback_url = self._resolve_playback_url(protocol, stream_endpoints)

        return StreamInfoResponse(
            camera_id=camera.id,
            camera_name=camera.name,
            stream_id=stream_id,
            stream_name=stream_endpoints.stream_name,
            stream_identifier=f"{camera.id}:{stream_id}",
            status=status,
            protocol=protocol,
            playback_url=playback_url,
            relative_playback_url=None,
            access_urls=StreamAccessUrls(
                webrtc_url=stream_endpoints.whep_url,
                hls_url=stream_endpoints.hls_url,
                rtsp_pull_url=stream_endpoints.rtsp_pull_url,
            ),
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
                sampled_frames=worker_snapshot.sampled_frames,
                dropped_frames=worker_snapshot.dropped_frames,
                current_fps=worker_snapshot.current_fps,
                queue_latency_ms=worker_snapshot.queue_latency_ms,
                decode_time_ms=worker_snapshot.decode_time_ms,
            ),
        )

    def _build_fallback(self, status: StreamStatus) -> StreamFallbackInfo | None:
        if status == StreamStatus.running:
            return None
        if status == StreamStatus.starting:
            return StreamFallbackInfo(
                kind="warming_up",
                message=(
                    "MediaMTX is warming up the camera path. "
                    "Subscribe to WebSocket updates and retry shortly."
                ),
                retry_after_seconds=2,
            )
        if status in {StreamStatus.reconnecting, StreamStatus.error, StreamStatus.crashed}:
            return StreamFallbackInfo(
                kind="retry",
                message=(
                    "The realtime worker is reconnecting to MediaMTX. "
                    "Keep the WebSocket open for status updates."
                ),
                retry_after_seconds=3,
            )
        return StreamFallbackInfo(
            kind="start_required",
            message="Stream is not active yet. Call the start endpoint before opening the player.",
            retry_after_seconds=None,
        )

    def _resolve_playback_url(
        self,
        protocol: StreamProtocol,
        stream_endpoints: MediaMtxStreamEndpoints,
    ) -> str:
        """Return the primary playback URL that frontend players should open first."""

        if self._protocol_value(protocol) == StreamProtocol.hls.value:
            return stream_endpoints.hls_url
        return stream_endpoints.whep_url

    @staticmethod
    def _protocol_value(protocol: StreamProtocol | str) -> str:
        """Normalize protocol values that may arrive as enums or plain strings."""

        return protocol.value if isinstance(protocol, StreamProtocol) else protocol

    def _websocket_public_url(self) -> str:
        if self._settings.public_ws_base_url:
            return f"{self._settings.public_ws_base_url.rstrip('/')}/streams/ws/updates"

        parsed = urlparse(self._settings.public_api_base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        websocket_base = urlunparse(
            parsed._replace(scheme=scheme, path="", params="", query="", fragment="")
        )
        return f"{websocket_base.rstrip('/')}/streams/ws/updates"
