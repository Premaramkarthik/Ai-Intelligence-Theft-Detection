"""Tests for managed MediaMTX orchestration."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from src.core.config import Settings
from src.core.exceptions.stream.stream_exceptions import MediaMtxStartupException
from src.models.camera import CameraRecord, CameraStatus, RTSPTransport, ValidationStatus
from src.services.realtime_video.mediamtx_control_api import MediaMtxControlApiException
from src.services.realtime_video.mediamtx_service import MediaMtxService


def test_rendered_mediamtx_config_contains_camera_sources() -> None:
    """Render per-camera MediaMTX paths from the stored camera inventory."""

    service = MediaMtxService(
        Settings(
            database_url="postgresql://postgres:postgres@localhost:5432/test_db",
            mediamtx_manage_process=True,
            mediamtx_api_password=SecretStr("control-secret"),
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
    assert '  - user: "backend-control"' in rendered
    assert '    pass: "control-secret"' in rendered


async def test_health_snapshot_reflects_configuration() -> None:
    """Return the configured MediaMTX config path through the health snapshot."""

    settings = Settings(
        database_url="postgresql://postgres:postgres@localhost:5432/test_db",
        mediamtx_generated_config_path="runtime/mediamtx.generated.yml",
        mediamtx_api_password=SecretStr("control-secret"),
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
        mediamtx_api_password=SecretStr("control-secret"),
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


async def test_sync_config_reconciles_runtime_paths_for_external_service(
    tmp_path,
    monkeypatch,
) -> None:
    """Synchronize runtime MediaMTX paths through the Control API in external-service mode."""

    settings = Settings(
        database_url="postgresql://postgres:postgres@localhost:5432/test_db",
        mediamtx_generated_config_path=tmp_path / "mediamtx.generated.yml",
        mediamtx_manage_process=False,
        mediamtx_api_password=SecretStr("control-secret"),
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
            metadata={"mediamtx_stream_name": "front-gate"},
            tags=[],
            last_validated_at=None,
            last_validation_status=ValidationStatus.unknown,
            last_validation_message=None,
        ),
    ]
    list_configured_paths = AsyncMock(return_value={"stale-path": {"name": "stale-path"}})
    upsert_path = AsyncMock()
    delete_path = AsyncMock()
    monkeypatch.setattr(
        service._control_api,  # pylint: disable=protected-access
        "list_configured_paths",
        list_configured_paths,
    )
    monkeypatch.setattr(
        service._control_api,  # pylint: disable=protected-access
        "upsert_path",
        upsert_path,
    )
    monkeypatch.setattr(
        service._control_api,  # pylint: disable=protected-access
        "delete_path",
        delete_path,
    )

    await service.sync_config(cameras)

    list_configured_paths.assert_awaited_once()
    upsert_path.assert_awaited_once()
    delete_path.assert_awaited_once_with("stale-path")
    path_name, payload, configured_paths = upsert_path.await_args.args
    assert path_name == "front-gate"
    assert payload["source"] == "rtsp://192.168.1.2:8080/h264_ulaw.sdp"
    assert payload["sourceOnDemand"] is True
    assert configured_paths == {"stale-path": {"name": "stale-path"}}


async def test_ensure_ready_requires_runtime_path_in_external_service(
    tmp_path,
    monkeypatch,
) -> None:
    """Fail fast when the requested runtime path has not been loaded into MediaMTX yet."""

    settings = Settings(
        database_url="postgresql://postgres:postgres@localhost:5432/test_db",
        mediamtx_generated_config_path=tmp_path / "mediamtx.generated.yml",
        mediamtx_manage_process=False,
        mediamtx_api_password=SecretStr("control-secret"),
        _env_file=None,
    )
    service = MediaMtxService(settings)
    camera = CameraRecord(
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
    )
    monkeypatch.setattr(
        service,
        "_sync_config_unlocked",
        AsyncMock(),
    )
    monkeypatch.setattr(
        service,
        "_is_rtsp_listener_ready",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        service._control_api,  # pylint: disable=protected-access
        "path_exists",
        AsyncMock(return_value=False),
    )

    with pytest.raises(MediaMtxStartupException) as exc_info:
        await service.ensure_ready([camera], camera)

    assert exc_info.value.error_code == "MEDIAMTX_START_FAILED"
    assert exc_info.value.details["stream_name"] == "front-gate"


async def test_sync_config_can_degrade_gracefully_during_startup(
    tmp_path,
    monkeypatch,
) -> None:
    """Allow backend startup to continue when external MediaMTX auth is not ready yet."""

    settings = Settings(
        database_url="postgresql://postgres:postgres@localhost:5432/test_db",
        mediamtx_generated_config_path=tmp_path / "mediamtx.generated.yml",
        mediamtx_manage_process=False,
        mediamtx_api_password=SecretStr("control-secret"),
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
            metadata={"mediamtx_stream_name": "front-gate"},
            tags=[],
            last_validated_at=None,
            last_validation_status=ValidationStatus.unknown,
            last_validation_message=None,
        ),
    ]
    monkeypatch.setattr(
        service,
        "_sync_runtime_paths_unlocked",
        AsyncMock(
            side_effect=MediaMtxStartupException(
                "MediaMTX runtime path synchronization failed through the "
                "Control API.",
                details={
                    "error": str(
                        MediaMtxControlApiException(
                            "MediaMTX Control API request failed with HTTP 401 "
                            "for /v3/config/paths/list.",
                            status_code=401,
                        ),
                    ),
                },
            ),
        ),
    )

    await service.sync_config(cameras, strict_runtime_sync=False)

    assert service.health_snapshot().last_error is None
