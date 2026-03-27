"""Tests for managed MediaMTX orchestration."""

from __future__ import annotations

from src.core.config import Settings
from src.models.camera import CameraRecord, CameraStatus, RTSPTransport, ValidationStatus
from src.services.realtime_video.mediamtx_service import MediaMtxService


def test_rendered_mediamtx_config_contains_camera_sources() -> None:
    """Render per-camera MediaMTX paths from the stored camera inventory."""

    service = MediaMtxService(
        Settings(
            database_url="postgresql://postgres:postgres@localhost:5432/test_db",
            mediamtx_manage_process=True,
            _env_file=None,
        ),
    )
    cameras = [
        CameraRecord(
            id="cam_1",
            name="Front Gate",
            location=None,
            host=None,
            port=None,
            username=None,
            password=None,
            path=None,
            direct_rtsp_url="rtsp://192.168.1.2:8080/h264_ulaw.sdp",
            transport=RTSPTransport.tcp,
            status=CameraStatus.active,
            metadata={"mediamtx_stream_name": "front-gate"},
            tags=[],
            last_validated_at=None,
            last_validation_status=ValidationStatus.unknown,
            last_validation_message=None,
        ),
    ]

    rendered = service._render_config(cameras)  # pylint: disable=protected-access

    assert "front-gate" in rendered
    assert 'source: "rtsp://192.168.1.2:8080/h264_ulaw.sdp"' in rendered
    assert "rtspAddress: :8554" in rendered
    assert "  useAbsoluteTimestamp: false" in rendered


async def test_health_snapshot_reflects_configuration() -> None:
    """Return the configured MediaMTX config path through the health snapshot."""

    settings = Settings(
        database_url="postgresql://postgres:postgres@localhost:5432/test_db",
        mediamtx_generated_config_path="runtime/mediamtx.generated.yml",
        _env_file=None,
    )
    service = MediaMtxService(settings)

    snapshot = service.health_snapshot()

    assert snapshot.managed is True
    assert snapshot.config_path.endswith("runtime/mediamtx.generated.yml")


async def test_sync_config_writes_generated_file(tmp_path) -> None:
    """Write the generated MediaMTX config file for externally managed deployments."""

    settings = Settings(
        database_url="postgresql://postgres:postgres@localhost:5432/test_db",
        mediamtx_generated_config_path=tmp_path / "mediamtx.generated.yml",
        _env_file=None,
    )
    service = MediaMtxService(settings)
    cameras = [
        CameraRecord(
            id="cam_1",
            name="Front Gate",
            location=None,
            host=None,
            port=None,
            username=None,
            password=None,
            path=None,
            direct_rtsp_url="rtsp://192.168.1.2:8080/h264_ulaw.sdp",
            transport=RTSPTransport.tcp,
            status=CameraStatus.active,
            metadata={},
            tags=[],
            last_validated_at=None,
            last_validation_status=ValidationStatus.unknown,
            last_validation_message=None,
        ),
    ]

    await service.sync_config(cameras)

    assert settings.mediamtx_generated_config_path.exists()
