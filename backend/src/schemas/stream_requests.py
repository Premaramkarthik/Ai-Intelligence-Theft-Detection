from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.models.camera import StreamProtocol


class StreamStartRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    force_restart: bool = False
    requested_protocol: StreamProtocol = StreamProtocol.webrtc
    sample_fps: float | None = Field(default=None, gt=0, le=60)
    enable_tracking_events: bool | None = None
    enable_inference: bool | None = None
    reason: str | None = Field(default=None, max_length=255)


class StreamStopRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)
