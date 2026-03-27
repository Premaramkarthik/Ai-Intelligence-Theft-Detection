from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from src.models.camera import CameraStatus, RTSPTransport
from src.schemas.camera_requests import CreateCameraRequest
from src.services.camera.camera_service import CameraService


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


class DummyMediaMtxService:
    def __init__(self) -> None:
        self.calls: list[list[object]] = []

    async def sync_config(self, cameras: list[object]) -> None:
        self.calls.append(cameras)


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
