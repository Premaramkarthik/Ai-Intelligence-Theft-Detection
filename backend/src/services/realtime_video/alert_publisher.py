"""Publish realtime stream connection alerts for frontend consumers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.logger.logger import get_logger
from src.models.camera import StreamDesiredState, StreamProtocol, StreamStatus
from src.schemas.common import WebSocketEnvelope
from src.schemas.stream_responses import StreamEventPayload
from src.services.camera.camera_service import CameraService
from src.services.presentation.stream_contract_service import StreamContractService
from src.services.presentation.websocket_manager import WebSocketManager
from src.services.realtime_video.mediamtx import normalize_stream_name
from src.services.stream.stream_repository import StreamRepository

if TYPE_CHECKING:
    from src.services.realtime_video.stream_manager import MediaMtxStreamManager


class WebSocketStreamConnectionAlertPublisher:  # pylint: disable=too-many-arguments,too-many-positional-arguments
    """Publish stream connection alerts through the existing websocket channel."""

    def __init__(
        self,
        camera_service: CameraService,
        stream_repository: StreamRepository,
        stream_manager: MediaMtxStreamManager,
        contract_service: StreamContractService,
        websocket_manager: WebSocketManager,
    ) -> None:
        """Create a publisher that rebuilds and broadcasts the current stream contract."""

        self._camera_service = camera_service
        self._stream_repository = stream_repository
        self._stream_manager = stream_manager
        self._contract_service = contract_service
        self._websocket_manager = websocket_manager
        self._logger = get_logger(__name__)

    async def publish_camera_connected(self, camera_id: str) -> None:
        """Persist and broadcast a websocket alert for a connected realtime stream."""

        camera = await self._camera_service.get_camera_record(camera_id)
        stream_name = normalize_stream_name(
            camera.metadata.get("mediamtx_stream_name") or camera.id,
        )
        stream_endpoints = self._stream_manager.stream_endpoints(stream_name)
        worker_snapshot = self._stream_manager.get_snapshot(camera_id)
        existing_record = await self._stream_repository.fetch_by_camera_id(camera_id)
        stream_record = await self._stream_repository.apply_event(
            StreamEventPayload(
                camera_id=camera.id,
                camera_name=camera.name,
                stream_id=f"stream_{camera.id}",
                event="stream_connected",
                status=StreamStatus.running,
                protocol=(
                    existing_record.protocol
                    if existing_record is not None
                    else StreamProtocol.webrtc
                ),
                message="Camera connected and realtime frames are flowing.",
                playback_url=(
                    existing_record.playback_path
                    if existing_record and existing_record.playback_path
                    else stream_endpoints.whep_url
                ),
                playlist_path=(
                    existing_record.playlist_path
                    if existing_record and existing_record.playlist_path
                    else stream_endpoints.hls_url
                ),
                desired_state=StreamDesiredState.running,
                reconnect_attempts=worker_snapshot.reconnect_attempts,
                restart_count=worker_snapshot.restart_count,
                metadata={
                    "stream_name": stream_name,
                    "webrtc_url": stream_endpoints.whep_url,
                    "hls_url": stream_endpoints.hls_url,
                    "rtsp_pull_url": stream_endpoints.rtsp_pull_url,
                    "alert_kind": "stream_connected",
                },
            ),
        )
        contract = self._contract_service.build_contract(
            camera,
            stream_record,
            worker_snapshot,
            stream_endpoints,
        )
        await self._websocket_manager.broadcast(
            WebSocketEnvelope(
                type="stream.connected",
                topic="stream_connected",
                message="Camera connected and realtime frames are flowing.",
                camera_id=camera.id,
                data=contract.model_dump(mode="json"),
            ),
        )
        self._logger.info("Broadcasted stream connection alert for %s.", camera.id)

    async def publish_camera_disconnected(
        self,
        camera_id: str,
        *,
        reconnect_attempts: int,
        error_message: str,
    ) -> None:
        """Persist and broadcast a terminal disconnect alert after reconnect exhaustion."""

        camera = await self._camera_service.get_camera_record(camera_id)
        stream_name = normalize_stream_name(
            camera.metadata.get("mediamtx_stream_name") or camera.id,
        )
        stream_endpoints = self._stream_manager.stream_endpoints(stream_name)
        existing_record = await self._stream_repository.fetch_by_camera_id(camera_id)
        stream_record = await self._stream_repository.apply_event(
            StreamEventPayload(
                camera_id=camera.id,
                camera_name=camera.name,
                stream_id=f"stream_{camera.id}",
                event="stream_disconnected",
                status=StreamStatus.stopped,
                protocol=(
                    existing_record.protocol
                    if existing_record is not None
                    else StreamProtocol.webrtc
                ),
                message=(
                    "Camera disconnected after exhausting the reconnect budget."
                ),
                playback_url=(
                    existing_record.playback_path
                    if existing_record and existing_record.playback_path
                    else stream_endpoints.whep_url
                ),
                playlist_path=(
                    existing_record.playlist_path
                    if existing_record and existing_record.playlist_path
                    else stream_endpoints.hls_url
                ),
                desired_state=StreamDesiredState.stopped,
                reconnect_attempts=reconnect_attempts,
                restart_count=0,
                error_code="RECONNECT_EXHAUSTED",
                error_message=error_message,
                metadata={
                    "stream_name": stream_name,
                    "webrtc_url": stream_endpoints.whep_url,
                    "hls_url": stream_endpoints.hls_url,
                    "rtsp_pull_url": stream_endpoints.rtsp_pull_url,
                    "alert_kind": "stream_disconnected",
                },
            ),
        )
        contract = self._contract_service.build_contract(
            camera,
            stream_record,
            self._stream_manager.get_snapshot(camera_id),
            stream_endpoints,
        )
        await self._websocket_manager.broadcast(
            WebSocketEnvelope(
                type="stream.disconnected",
                topic="stream_disconnected",
                message=(
                    "Camera disconnected after exhausting the reconnect budget."
                ),
                camera_id=camera.id,
                data=contract.model_dump(mode="json"),
            ),
        )
        self._logger.info("Broadcasted stream disconnect alert for %s.", camera.id)
