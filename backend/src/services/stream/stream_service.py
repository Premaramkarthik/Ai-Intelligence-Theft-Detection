from __future__ import annotations

from pathlib import Path

from src.core.config import Settings
from src.core.exceptions.stream.stream_exceptions import StreamNotRunningException
from src.models.camera import (
    StreamDesiredState,
    StreamProtocol,
    StreamStatus,
)
from src.schemas.common import HealthComponent, WebSocketEnvelope
from src.schemas.stream_requests import StreamStartRequest, StreamStopRequest
from src.schemas.stream_responses import StreamEventPayload, StreamInfoResponse
from src.services.camera.camera_service import CameraService
from src.services.presentation.stream_contract_service import StreamContractService
from src.services.stream.stream_manager import StreamManager
from src.services.stream.stream_repository import StreamRepository
from src.utils.ffmpeg import build_hls_output_paths, build_rtsp_url_from_camera


class StreamService:
    def __init__(
        self,
        settings: Settings,
        camera_service: CameraService,
        stream_repository: StreamRepository,
        stream_manager: StreamManager,
        contract_service: StreamContractService,
    ) -> None:
        self._settings = settings
        self._camera_service = camera_service
        self._stream_repository = stream_repository
        self._stream_manager = stream_manager
        self._contract_service = contract_service

    async def start_stream(self, camera_id: str, request: StreamStartRequest) -> StreamInfoResponse:
        camera = await self._camera_service.get_camera_record(camera_id)
        rtsp_url = build_rtsp_url_from_camera(camera)
        output_dir, playlist_path = build_hls_output_paths(
            self._settings.media_root,
            self._settings.hls_directory_name,
            camera_id,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        relative_playback_url = self._relative_playback_url(camera_id)
        await self._stream_repository.upsert_requested_state(
            camera_id=camera.id,
            stream_id=f"stream_{camera.id}",
            status=StreamStatus.starting.value,
            desired_state=StreamDesiredState.running.value,
            protocol=StreamProtocol.hls.value,
            playback_path=relative_playback_url,
            playlist_path=str(playlist_path),
            metadata={"reason": request.reason} if request.reason else {},
        )
        worker_snapshot = await self._stream_manager.start_worker(
            camera=camera,
            rtsp_url=rtsp_url,
            request=request,
            playback_path=relative_playback_url,
            playlist_path=str(playlist_path),
        )
        stream_record = await self._stream_repository.fetch_by_camera_id(camera.id)
        return self._contract_service.build_contract(camera, stream_record, worker_snapshot)

    async def stop_stream(
        self,
        camera_id: str,
        request: StreamStopRequest | None = None,
    ) -> StreamInfoResponse:
        camera = await self._camera_service.get_camera_record(camera_id)
        try:
            worker_snapshot = await self._stream_manager.stop_worker(camera_id)
        except StreamNotRunningException:
            worker_snapshot = self._stream_manager.get_snapshot(camera_id)

        stream_record = await self._stream_repository.update_requested_state(
            camera_id=camera_id,
            status=StreamStatus.stopping.value,
            desired_state=StreamDesiredState.stopped.value,
            metadata={"reason": request.reason} if request and request.reason else {},
        )
        return self._contract_service.build_contract(camera, stream_record, worker_snapshot)

    async def get_stream_status(self, camera_id: str) -> StreamInfoResponse:
        camera = await self._camera_service.get_camera_record(camera_id)
        stream_record = await self._stream_repository.fetch_by_camera_id(camera_id)
        worker_snapshot = self._stream_manager.get_snapshot(camera_id)
        return self._contract_service.build_contract(camera, stream_record, worker_snapshot)

    async def get_stream_info(self, camera_id: str) -> StreamInfoResponse:
        return await self.get_stream_status(camera_id)

    async def list_stream_contracts(self, camera_id: str | None = None) -> list[StreamInfoResponse]:
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
            )
            for camera in cameras
        ]

    async def apply_stream_event(self, event: StreamEventPayload) -> StreamInfoResponse:
        stream_record = await self._stream_repository.apply_event(event)
        self._stream_manager.note_event(
            camera_id=event.camera_id,
            reconnect_attempts=event.reconnect_attempts,
            restart_count=event.restart_count,
        )
        camera = await self._camera_service.get_camera_record(event.camera_id)
        worker_snapshot = self._stream_manager.get_snapshot(event.camera_id)
        return self._contract_service.build_contract(camera, stream_record, worker_snapshot)

    async def build_websocket_event(self, event: StreamEventPayload) -> WebSocketEnvelope:
        contract = await self.apply_stream_event(event)
        return WebSocketEnvelope(
            type="stream.updated",
            topic=event.event,
            message=event.message,
            camera_id=event.camera_id,
            data=contract.model_dump(mode="json"),
        )

    async def get_stream_health(self, camera_id: str) -> HealthComponent:
        camera = await self._camera_service.get_camera_record(camera_id)
        stream_record = await self._stream_repository.fetch_by_camera_id(camera_id)
        playlist_path = self._playlist_path(camera.id)
        playlist_exists = playlist_path.exists()
        worker_snapshot = self._stream_manager.get_snapshot(camera_id)

        if stream_record and stream_record.status == StreamStatus.running and playlist_exists:
            return HealthComponent(
                status="ok",
                message="Stream is healthy and HLS output is present.",
                details={
                    "playlist_path": str(playlist_path),
                    "worker_pid": worker_snapshot.process_id,
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
                "playlist_exists": playlist_exists,
                "worker_alive": worker_snapshot.is_process_alive,
            },
        )

    def _relative_playback_url(self, camera_id: str) -> str:
        return (
            f"{self._settings.media_mount_path}/"
            f"{self._settings.hls_directory_name}/{camera_id}/index.m3u8"
        )

    def _playlist_path(self, camera_id: str) -> Path:
        _output_dir, playlist_path = build_hls_output_paths(
            self._settings.media_root,
            self._settings.hls_directory_name,
            camera_id,
        )
        return playlist_path
