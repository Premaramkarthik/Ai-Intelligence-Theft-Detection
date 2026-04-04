from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.models.camera import StreamDesiredState, StreamProtocol, StreamStatus
from src.schemas.common import utc_now
from src.schemas.inference_events import InferenceStateResponse


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
    sampled_frames: int = 0
    dropped_frames: int = 0
    current_fps: float = 0.0
    queue_latency_ms: float = 0.0
    decode_time_ms: float = 0.0


class StreamAccessUrls(BaseModel):
    webrtc_url: str
    hls_url: str
    rtsp_pull_url: str


class TrackingTrackResponse(BaseModel):
    track_id: str
    persistent_id: str | None = None
    class_name: str | None = None
    confidence: float
    similarity: float | None = None
    left: int
    top: int
    width: int
    height: int


class TrackingStateResponse(BaseModel):
    enabled: bool = False
    stream_name: str | None = None
    access_urls: StreamAccessUrls | None = None
    is_registered: bool = False
    is_process_alive: bool = False
    reconnect_attempts: int = 0
    active_tracks: int = 0
    identity_backend: str = "milvus"
    last_error_message: str | None = None
    tracks: list[TrackingTrackResponse] = Field(default_factory=list)



class StreamInfoResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    camera_id: str
    camera_name: str
    stream_id: str
    stream_name: str
    stream_identifier: str
    status: StreamStatus
    protocol: StreamProtocol
    playback_url: str | None = None
    relative_playback_url: str | None = None
    access_urls: StreamAccessUrls
    websocket_url: str
    fallback: StreamFallbackInfo | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    last_event_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    tracking: TrackingStateResponse | None = None
    inference: InferenceStateResponse | None = None
    worker: WorkerStateResponse


class StreamEventPayload(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    camera_id: str
    camera_name: str
    stream_id: str
    event: str
    status: StreamStatus
    protocol: StreamProtocol = StreamProtocol.webrtc
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
