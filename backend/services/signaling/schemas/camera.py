"""Pydantic schemas for camera-related data."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class ROIConfigRequest(BaseModel):
    roi: Optional[dict] = Field(default_factory=dict)
    confidence_threshold: float = 0.45
    iou_threshold: float = 0.15
    hand_dist_px: int = 80
    enabled: bool = True


class ROIConfigResponse(ROIConfigRequest):
    camera_id: str


class RTSPConfig(BaseModel):
    username: str
    password: str
    ip_address: str
    port: int = 554
    substreams: list[str] = Field(default_factory=list)


class CameraConnectRequest(BaseModel):
    source_type: str # "rtsp" or "webcam"
    rtsp_config: Optional[RTSPConfig] = None
    device_index: Optional[int] = 0


class ConnectResponse(BaseModel):
    status: str
    message: str
    stream_ids: list[str] = Field(default_factory=list)
