from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.models.camera import CameraStatus, RTSPTransport, StreamStatus, ValidationStatus


class CameraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: str
    name: str
    location: str | None
    host: str | None
    port: int | None
    path: str | None
    source_mode: str
    rtsp_url_preview: str
    transport: RTSPTransport
    status: CameraStatus
    stream_status: StreamStatus | None = None
    has_credentials: bool
    metadata: dict[str, Any]
    tags: list[str]
    last_validated_at: datetime | None
    last_validation_status: ValidationStatus
    last_validation_message: str | None
    created_at: datetime | None
    updated_at: datetime | None


class CameraValidationResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    camera_id: str
    camera_name: str
    is_reachable: bool
    code: str
    message: str
    resolved_rtsp_url_preview: str
    latency_ms: int | None = None
    details: dict[str, Any] | None = None
    validated_at: datetime
