from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.models.camera import StreamProtocol


class StreamStartRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    force_restart: bool = False
    requested_protocol: StreamProtocol = StreamProtocol.hls
    enable_tracking_events: bool | None = None
    reason: str | None = Field(default=None, max_length=255)


class StreamStopRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)
