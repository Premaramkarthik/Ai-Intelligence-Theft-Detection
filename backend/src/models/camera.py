from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class CameraStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    error = "error"


class ValidationStatus(str, Enum):
    unknown = "unknown"
    reachable = "reachable"
    unreachable = "unreachable"


class StreamStatus(str, Enum):
    stopped = "stopped"
    starting = "starting"
    running = "running"
    stopping = "stopping"
    reconnecting = "reconnecting"
    error = "error"
    crashed = "crashed"


class StreamDesiredState(str, Enum):
    running = "running"
    stopped = "stopped"


class StreamProtocol(str, Enum):
    webrtc = "webrtc"
    hls = "hls"


class RTSPTransport(str, Enum):
    tcp = "tcp"
    udp = "udp"


@dataclass(slots=True)
class CameraRecord:
    id: str
    name: str
    location: str | None
    host: str | None
    port: int | None
    username: str | None
    password: str | None
    path: str | None
    direct_rtsp_url: str | None
    transport: RTSPTransport
    status: CameraStatus
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    last_validated_at: datetime | None = None
    last_validation_status: ValidationStatus = ValidationStatus.unknown
    last_validation_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    stream_status: StreamStatus | None = None
    stream_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StreamRecord:
    camera_id: str
    stream_id: str
    status: StreamStatus
    desired_state: StreamDesiredState
    protocol: StreamProtocol
    playback_path: str | None
    playlist_path: str | None
    worker_pid: int | None
    worker_started_at: datetime | None
    last_event_at: datetime | None
    last_heartbeat_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    restart_count: int = 0
    reconnect_attempts: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
