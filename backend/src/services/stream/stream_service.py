from __future__ import annotations

from src.core.config import Settings
from src.models.camera import (
    CameraRecord,
    StreamDesiredState,
    StreamProtocol,
    StreamStatus,
)
from src.schemas.common import HealthComponent, WebSocketEnvelope
from src.schemas.stream_requests import StreamStartRequest, StreamStopRequest
from src.schemas.stream_responses import (
    StreamEventPayload,
    StreamInfoResponse,
)
from src.services.camera.camera_service import CameraService
from src.services.presentation.stream_contract_service import StreamContractService
from src.services.inference.manager import InferenceManager
from src.services.realtime_video.contracts import MediaMtxStreamEndpoints
from src.services.realtime_video.mediamtx import normalize_stream_name
from src.services.realtime_video.mediamtx_service import MediaMtxService
from src.services.realtime_video.stream_manager import MediaMtxStreamManager
from src.services.stream.stream_repository import StreamRepository
from src.services.tracking.manager import TrackingStreamManager


class StreamService:
    def __init__(
        self,
        settings: Settings,
        camera_service: CameraService,
        stream_repository: StreamRepository,
        mediamtx_service: MediaMtxService,
        stream_manager: MediaMtxStreamManager,
        tracking_manager: TrackingStreamManager,
        inference_manager: InferenceManager,
        contract_service: StreamContractService,
    ) -> None:
        """Create the stream control service for MediaMTX-backed playback and extraction."""

        self._settings = settings
        self._camera_service = camera_service
        self._stream_repository = stream_repository
        self._mediamtx_service = mediamtx_service
        self._stream_manager = stream_manager
        self._tracking_manager = tracking_manager
        self._inference_manager = inference_manager
        self._contract_service = contract_service

    async def start_stream(self, camera_id: str, request: StreamStartRequest) -> StreamInfoResponse:
        """Start frame extraction for a camera and return MediaMTX playback endpoints."""

        camera = await self._camera_service.ensure_camera_reachable(
            camera_id,
            timeout_seconds=self._settings.validation_timeout_seconds,
        )
        cameras = await self._camera_service.list_all_camera_records()
        await self._mediamtx_service.sync_config(cameras)
        await self._mediamtx_service.ensure_ready(cameras, camera)
        stream_name = self._stream_name(camera)
        stream_endpoints = self._stream_manager.stream_endpoints(stream_name)
        if request.force_restart:
            await self._stream_manager.stop_stream(camera.id)
            await self._tracking_manager.stop_stream(camera.id)
        playback_url = self._playback_url_for_protocol(
            request.requested_protocol,
            stream_endpoints.whep_url,
            stream_endpoints.hls_url,
        )
        await self._stream_repository.upsert_requested_state(
            camera_id=camera.id,
            stream_id=f"stream_{camera.id}",
            status=StreamStatus.running.value,
            desired_state=StreamDesiredState.running.value,
            protocol=self._enum_value(request.requested_protocol),
            playback_path=playback_url,
            playlist_path=stream_endpoints.hls_url,
            metadata=self._stream_metadata(
                stream_name=stream_name,
                stream_endpoints=stream_endpoints,
                reason=request.reason,
            ),
        )
        await self._stream_manager.start_stream(
            camera_id=camera.id,
            stream_name=stream_name,
            sample_fps=request.sample_fps or self._settings.realtime_frame_sample_fps,
        )
        tracking_requested = (
            self._settings.tracking_enabled_by_default
            if request.enable_tracking_events is None
            else request.enable_tracking_events
        )
        if tracking_requested:
            await self._tracking_manager.start_stream(camera.id, stream_name)
        else:
            await self._tracking_manager.stop_stream(camera.id)
        inference_requested = bool(tracking_requested and request.enable_inference)
        await self._inference_manager.configure_stream(
            camera.id,
            enabled=inference_requested,
        )
        worker_snapshot = self._stream_manager.get_snapshot(camera.id)
        tracking_snapshot = self._tracking_manager.get_snapshot(camera.id, stream_name)
        inference_snapshot = self._inference_manager.get_snapshot(camera.id)
        stream_record = await self._stream_repository.fetch_by_camera_id(camera.id)
        return self._contract_service.build_contract(
            camera,
            stream_record,
            worker_snapshot,
            stream_endpoints,
            tracking_snapshot,
            self._tracking_manager.stream_endpoints(stream_name),
            inference_snapshot,
        )

    async def stop_stream(
        self,
        camera_id: str,
        request: StreamStopRequest | None = None,
    ) -> StreamInfoResponse:
        """Stop frame extraction for a camera and preserve MediaMTX access metadata."""

        camera = await self._camera_service.get_camera_record(camera_id)
        stream_name = self._stream_name(camera)
        stream_endpoints = self._stream_manager.stream_endpoints(stream_name)
        await self._stream_manager.stop_stream(camera_id)
        await self._tracking_manager.stop_stream(camera_id)
        await self._inference_manager.configure_stream(camera_id, enabled=False)
        worker_snapshot = self._stream_manager.get_snapshot(camera_id)
        tracking_snapshot = self._tracking_manager.get_snapshot(camera.id, stream_name)
        inference_snapshot = self._inference_manager.get_snapshot(camera.id)

        stream_record = await self._stream_repository.update_requested_state(
            camera_id=camera_id,
            status=StreamStatus.stopped.value,
            desired_state=StreamDesiredState.stopped.value,
            metadata=self._stream_metadata(
                stream_name=stream_name,
                stream_endpoints=stream_endpoints,
                reason=request.reason if request else None,
            ),
        )
        return self._contract_service.build_contract(
            camera,
            stream_record,
            worker_snapshot,
            stream_endpoints,
            tracking_snapshot,
            self._tracking_manager.stream_endpoints(stream_name),
            inference_snapshot,
        )

    async def get_stream_status(self, camera_id: str) -> StreamInfoResponse:
        """Return the current stream status and MediaMTX playback contract."""

        camera = await self._camera_service.get_camera_record(camera_id)
        stream_record = await self._stream_repository.fetch_by_camera_id(camera_id)
        worker_snapshot = self._stream_manager.get_snapshot(camera_id)
        stream_name = self._stream_name(camera)
        return self._contract_service.build_contract(
            camera,
            stream_record,
            worker_snapshot,
            self._stream_manager.stream_endpoints(stream_name),
            self._tracking_manager.get_snapshot(camera_id, stream_name),
            self._tracking_manager.stream_endpoints(stream_name),
            self._inference_manager.get_snapshot(camera_id),
        )

    async def get_stream_info(self, camera_id: str) -> StreamInfoResponse:
        """Return the frontend-ready playback contract for a camera stream."""

        return await self.get_stream_status(camera_id)

    async def list_stream_contracts(self, camera_id: str | None = None) -> list[StreamInfoResponse]:
        """Return stream contracts for one camera or for the full camera inventory."""

        if camera_id:
            return [await self.get_stream_status(camera_id)]

        cameras = await self._camera_service.list_all_camera_records()
        stream_records = {
            record.camera_id: record
            for record in await self._stream_repository.list_streams()
        }
        return [
            self._contract_service.build_contract(
                camera,
                stream_records.get(camera.id),
                self._stream_manager.get_snapshot(camera.id),
                self._stream_manager.stream_endpoints(self._stream_name(camera)),
                self._tracking_manager.get_snapshot(camera.id, self._stream_name(camera)),
                self._tracking_manager.stream_endpoints(self._stream_name(camera)),
                self._inference_manager.get_snapshot(camera.id),
            )
            for camera in cameras
        ]

    async def apply_stream_event(self, event: StreamEventPayload) -> StreamInfoResponse:
        """Apply a stream lifecycle event and rebuild the current frontend contract."""

        stream_record = await self._stream_repository.apply_event(event)
        camera = await self._camera_service.get_camera_record(event.camera_id)
        worker_snapshot = self._stream_manager.get_snapshot(event.camera_id)
        return self._contract_service.build_contract(
            camera,
            stream_record,
            worker_snapshot,
            self._stream_manager.stream_endpoints(self._stream_name(camera)),
            self._tracking_manager.get_snapshot(event.camera_id, self._stream_name(camera)),
            self._tracking_manager.stream_endpoints(self._stream_name(camera)),
            self._inference_manager.get_snapshot(event.camera_id),
        )

    async def build_websocket_event(self, event: StreamEventPayload) -> WebSocketEnvelope:
        """Translate a stream lifecycle event into the frontend WebSocket envelope."""

        contract = await self.apply_stream_event(event)
        return WebSocketEnvelope(
            type="stream.updated",
            topic=event.event,
            message=event.message,
            camera_id=event.camera_id,
            data=contract.model_dump(mode="json"),
        )

    async def get_stream_health(self, camera_id: str) -> HealthComponent:
        """Report worker and contract health for a MediaMTX-backed camera stream."""

        camera = await self._camera_service.get_camera_record(camera_id)
        stream_record = await self._stream_repository.fetch_by_camera_id(camera_id)
        worker_snapshot = self._stream_manager.get_snapshot(camera_id)

        if (
            stream_record
            and stream_record.status == StreamStatus.running
            and worker_snapshot.is_process_alive
        ):
            return HealthComponent(
                status="ok",
                message="Stream is healthy and the realtime frame worker is active.",
                details={
                    "stream_name": self._stream_name(camera),
                    "webrtc_url": self._stream_manager.stream_endpoints(
                        self._stream_name(camera),
                    ).whep_url,
                },
            )

        return HealthComponent(
            status="degraded",
            message="Stream is not fully healthy.",
            details={
                "camera_id": camera.id,
                "status": (
                    stream_record.status.value
                    if stream_record
                    else StreamStatus.stopped.value
                ),
                "worker_alive": worker_snapshot.is_process_alive,
            },
        )

    @staticmethod
    def _enum_value(value: StreamProtocol) -> str:
        """Return a stable string representation for enum-backed protocol fields."""

        return value.value if isinstance(value, StreamProtocol) else str(value)

    @staticmethod
    def _playback_url_for_protocol(
        protocol: StreamProtocol,
        webrtc_url: str,
        hls_url: str,
    ) -> str:
        """Pick the primary playback URL that matches the requested frontend protocol."""

        if StreamService._protocol_value(protocol) == StreamProtocol.hls.value:
            return hls_url
        return webrtc_url

    @staticmethod
    def _stream_metadata(
        *,
        stream_name: str,
        stream_endpoints: MediaMtxStreamEndpoints,
        reason: str | None,
    ) -> dict[str, str]:
        """Persist the MediaMTX routing details alongside stream lifecycle state."""

        metadata = {
            "stream_name": stream_name,
            "webrtc_url": stream_endpoints.whep_url,
            "hls_url": stream_endpoints.hls_url,
            "rtsp_pull_url": stream_endpoints.rtsp_pull_url,
        }
        if reason:
            metadata["reason"] = reason
        return metadata

    @staticmethod
    def _stream_name(camera: CameraRecord) -> str:
        """Return the MediaMTX path name configured for a camera."""

        metadata_name = camera.metadata.get("mediamtx_stream_name")
        if isinstance(metadata_name, str) and metadata_name.strip():
            return normalize_stream_name(metadata_name)
        return normalize_stream_name(camera.id)

    @staticmethod
    def _protocol_value(protocol: StreamProtocol | str) -> str:
        """Normalize protocol values that may arrive as enums or plain strings."""

        return protocol.value if isinstance(protocol, StreamProtocol) else protocol
