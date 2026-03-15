"""Pydantic schemas for camera-related data."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ROIConfigRequest(BaseModel):
    organization_id: str = "default-org"
    store_id: str = "main-store"
    roi: Optional[dict] = Field(default_factory=dict)
    confidence_threshold: float = 0.45
    iou_threshold: float = 0.15
    hand_dist_px: int = 80
    interaction_frames: int = 5
    enabled: bool = True


class ROIConfigResponse(ROIConfigRequest):
    camera_id: str
    organization_id: str = "default-org"
    store_id: str = "main-store"


class RTSPConfig(BaseModel):
    rtsp_url: str

    @field_validator("rtsp_url")
    @classmethod
    def validate_rtsp_url(cls, value: str) -> str:
        value = value.strip()
        lowered = value.lower()
        if not lowered.startswith(("rtsp://", "rtsps://")):
            raise ValueError("RTSP URL must start with rtsp:// or rtsps://")
        if len(value) > 2048:
            raise ValueError("RTSP URL is too long")
        return value


class CameraConnectRequest(BaseModel):
    source_type: str  # "rtsp" or "webcam"
    rtsp_config: Optional[RTSPConfig] = None
    organization_id: str = "default-org"
    store_id: str = "main-store"

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"rtsp", "webcam"}:
            raise ValueError("source_type must be rtsp or webcam")
        return value


class ConnectResponse(BaseModel):
    status: str
    message: str
    stream_ids: list[str] = Field(default_factory=list)
    organization_id: str = "default-org"
    store_id: str = "main-store"
