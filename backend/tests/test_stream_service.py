from __future__ import annotations

from types import SimpleNamespace

import pytest
from src.core.exceptions.camera.camera_exceptions import CameraSourceUnavailableException
from src.schemas.stream_requests import StreamStartRequest
from src.services.stream.stream_service import StreamService


class DummyCameraService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None]] = []

    async def ensure_camera_reachable(self, camera_id: str, timeout_seconds: int | None = None):
        self.calls.append((camera_id, timeout_seconds))
        raise CameraSourceUnavailableException(
            camera_id,
            "The RTSP endpoint could not be validated.",
            details={"validation_code": "RTSP_UNREACHABLE"},
        )


class DummyStreamRepository:
    def __init__(self) -> None:
        self.called = False

    async def upsert_requested_state(self, **kwargs):
        self.called = True
        return kwargs


class DummyMediaMtxService:
    def __init__(self) -> None:
        self.sync_called = False
        self.ensure_called = False

    async def sync_config(self, cameras) -> None:
        self.sync_called = True
        del cameras

    async def ensure_ready(self, cameras, camera) -> None:
        self.ensure_called = True
        del cameras, camera


class DummyStreamManager:
    def __init__(self) -> None:
        self.called = False

    async def start_stream(self, camera_id: str, stream_name: str, sample_fps: float = 5.0) -> None:
        self.called = True
        del camera_id, stream_name, sample_fps


class DummyTrackingManager:
    def __init__(self) -> None:
        self.called = False

    async def start_stream(self, camera_id: str, stream_name: str) -> None:
        self.called = True
        del camera_id, stream_name


class DummyInferenceManager:
    def configure_camera(self, camera_id: str, metadata: dict | None) -> None:
        del camera_id, metadata

    async def warm_camera(self, camera_id: str) -> None:
        del camera_id


@pytest.mark.asyncio
async def test_start_stream_fails_fast_when_camera_source_is_unreachable() -> None:
    camera_service = DummyCameraService()
    stream_repository = DummyStreamRepository()
    mediamtx_service = DummyMediaMtxService()
    stream_manager = DummyStreamManager()
    tracking_manager = DummyTrackingManager()
    inference_manager = DummyInferenceManager()
    service = StreamService(
        settings=SimpleNamespace(
            validation_timeout_seconds=8,
            realtime_frame_sample_fps=5.0,
            tracking_enabled_by_default=True,
        ),
        camera_service=camera_service,
        stream_repository=stream_repository,
        mediamtx_service=mediamtx_service,
        stream_manager=stream_manager,
        tracking_manager=tracking_manager,
        inference_manager=inference_manager,
        contract_service=SimpleNamespace(),
    )

    with pytest.raises(CameraSourceUnavailableException) as exc_info:
        await service.start_stream("cam_123", StreamStartRequest())

    assert exc_info.value.error_code == "CAMERA_SOURCE_UNAVAILABLE"
    assert camera_service.calls == [("cam_123", 8)]
    assert stream_repository.called is False
    assert mediamtx_service.sync_called is False
    assert mediamtx_service.ensure_called is False
    assert stream_manager.called is False
    assert tracking_manager.called is False
