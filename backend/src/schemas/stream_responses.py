from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.models.camera import StreamDesiredState, StreamProtocol, StreamStatus
from src.schemas.common import utc_now


class StreamFallbackInfo(BaseModel):
    kind: str
    message: str
    retry_after_seconds: int | None = None


class WorkerStateResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    desired_state: StreamDesiredState
    is_registered: bool
    is_process_alive: bool
    process_id: int | None = None
    restart_count: int = 0
    reconnect_attempts: int = 0


class StreamInfoResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    camera_id: str
    camera_name: str
    stream_id: str
    stream_identifier: str
    status: StreamStatus
    protocol: StreamProtocol
    playback_url: str | None = None
    relative_playback_url: str | None = None
    websocket_url: str
    fallback: StreamFallbackInfo | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    last_event_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    worker: WorkerStateResponse


class StreamEventPayload(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    camera_id: str
    camera_name: str
    stream_id: str
    event: str
    status: StreamStatus
    protocol: StreamProtocol = StreamProtocol.hls
    message: str
    playback_url: str | None = None
    playlist_path: str | None = None
    process_id: int | None = None
    desired_state: StreamDesiredState = StreamDesiredState.running
    reconnect_attempts: int = 0
    restart_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    tracking_enabled: bool = False
    tracks: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utc_now)
