from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from src.core.exceptions.camera.camera_exceptions import CameraSourceUnavailableException
from src.models.camera import CameraStatus, RTSPTransport, ValidationStatus
from src.schemas.camera_requests import CreateCameraRequest
from src.services.camera.camera_service import CameraService
from src.services.camera.camera_validator import CameraValidationResult


class DummyRepository:
    def __init__(self) -> None:
        self.insert_kwargs: dict[str, object] | None = None
        self.items: list[object] = []

    async def insert(self, **kwargs):
        self.insert_kwargs = kwargs
        record = SimpleNamespace(
            id=kwargs["camera_id"],
            name=kwargs["name"],
            location=kwargs["location"],
            host=kwargs["host"],
            port=kwargs["port"],
            username=kwargs["username"],
            password=kwargs["password"],
            path=kwargs["path"],
            direct_rtsp_url=kwargs["direct_rtsp_url"],
            transport=RTSPTransport(kwargs["transport"]),
            status=CameraStatus(kwargs["status"]),
            metadata=kwargs["metadata"],
            tags=kwargs["tags"],
            last_validated_at=None,
            last_validation_status="unknown",
            last_validation_message=None,
            created_at=None,
            updated_at=None,
            stream_status=None,
        )
        self.items.append(record)
        return record

    async def list(self, status=None, search=None, limit=100, offset=0):
        del status, search, limit, offset
        return self.items, len(self.items)

    async def fetch_by_id(self, camera_id: str):
        return next((item for item in self.items if item.id == camera_id), None)

    async def update_validation_status(
        self,
        camera_id: str,
        validation_status: str,
        validation_message: str,
    ):
        record = await self.fetch_by_id(camera_id)
        if record is None:
            return None
        record.last_validated_at = datetime.now(timezone.utc)
        record.last_validation_status = ValidationStatus(validation_status)
        record.last_validation_message = validation_message
        return record


class DummyMediaMtxService:
    def __init__(self) -> None:
        self.calls: list[list[object]] = []

    async def sync_config(self, cameras: list[object]) -> None:
        self.calls.append(cameras)


class DummyValidator:
    def __init__(self, result: CameraValidationResult) -> None:
        self.result = result
        self.calls: list[tuple[object, int | None]] = []

    async def validate(self, camera, timeout_seconds: int | None = None):
        self.calls.append((camera, timeout_seconds))
        return self.result


@pytest.mark.asyncio
async def test_create_camera_accepts_string_enum_payload_values() -> None:
    repository = DummyRepository()
    mediamtx_service = DummyMediaMtxService()
    service = CameraService(
        repository,
        validator=SimpleNamespace(),
        mediamtx_service=mediamtx_service,
    )
    payload = CreateCameraRequest(
        name="Front Gate",
        location="Gate",
        host="camera.local",
        path="/stream",
        port=554,
        username="user",
        password=SecretStr("secret"),
        transport="tcp",
        status="inactive",
        metadata={"additionalProp1": {}},
        tags=["entry"],
    )

    response = await service.create_camera(payload)

    assert repository.insert_kwargs is not None
    assert repository.insert_kwargs["transport"] == "tcp"
    assert repository.insert_kwargs["status"] == "inactive"
    assert response.name == "Front Gate"
    assert len(mediamtx_service.calls) == 1
    assert mediamtx_service.calls[0][0].direct_rtsp_url is None


@pytest.mark.asyncio
async def test_ensure_camera_reachable_persists_unreachable_validation() -> None:
    repository = DummyRepository()
    mediamtx_service = DummyMediaMtxService()
    validator = DummyValidator(
        CameraValidationResult(
            is_reachable=False,
            code="RTSP_UNREACHABLE",
            message="The RTSP endpoint could not be validated.",
            resolved_rtsp_url_preview="rtsp://camera.local/stream",
            latency_ms=145,
            details={"stderr": "Connection refused"},
            validated_at=datetime.now(timezone.utc),
        ),
    )
    service = CameraService(
        repository,
        validator=validator,
        mediamtx_service=mediamtx_service,
    )
    camera = await service.create_camera(
        CreateCameraRequest(
            name="Front Gate",
            location="Gate",
            host="camera.local",
            path="/stream",
            port=554,
            username="user",
            password=SecretStr("secret"),
            transport="tcp",
            status="inactive",
            metadata={"additionalProp1": {}},
            tags=["entry"],
        ),
    )

    with pytest.raises(CameraSourceUnavailableException) as exc_info:
        await service.ensure_camera_reachable(camera.id, timeout_seconds=3)

    assert exc_info.value.error_code == "CAMERA_SOURCE_UNAVAILABLE"
    assert repository.items[0].last_validation_status == ValidationStatus.unreachable
    assert (
        repository.items[0].last_validation_message
        == "The RTSP endpoint could not be validated."
    )
    assert validator.calls[0][1] == 3
