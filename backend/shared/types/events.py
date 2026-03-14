from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MessageType(StrEnum):
    FRAME_TELEMETRY = "telemetry.frame"
    INCIDENT_EVENT = "incident.event"
    CAMERA_STREAM = "camera.stream"
    STATUS = "system.status"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FrameReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_id: str
    slot_id: int
    generation: int


class DetectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bbox: list[float]
    label: str
    confidence: float
    track_id: str | int | None = None


class IncidentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    confidence: float
    severity: Severity


class FrameTelemetryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION)
    message_type: MessageType = Field(default=MessageType.FRAME_TELEMETRY)
    camera_id: str
    trace_id: str
    timestamp: str
    capture_timestamp: float
    detections: list[DetectionPayload] = Field(default_factory=list)
    incident: IncidentPayload | None = None
    frame_ref: FrameReference
    metadata: dict[str, Any] = Field(default_factory=dict)


class IncidentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION)
    message_type: MessageType = Field(default=MessageType.INCIDENT_EVENT)
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str = "shoplifting.detected"
    camera_id: str
    trace_id: str
    timestamp: str
    label: str
    confidence: float
    severity: Severity
    detections: list[DetectionPayload] = Field(default_factory=list)
    frame_ref: FrameReference
    metadata: dict[str, Any] = Field(default_factory=dict)


class CameraStreamMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION)
    message_type: MessageType = Field(default=MessageType.CAMERA_STREAM)
    camera_id: str
    timestamp: str
    image_jpeg_base64: str
    detections: list[DetectionPayload] = Field(default_factory=list)
    incident: IncidentPayload | None = None


class HistoryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    camera_id: str
    trace_id: str
    timestamp: str
    label: str
    confidence: float
    severity: Severity
    event_type: str
    detections: list[DetectionPayload] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
