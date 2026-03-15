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
    CAMERA_METADATA = "camera.metadata"
    STATUS = "system.status"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    NEEDS_REVIEW = "needs_review"


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
    organization_id: str = "default-org"
    store_id: str = "main-store"
    trace_id: str
    timestamp: str
    label: str
    confidence: float
    severity: Severity
    detections: list[DetectionPayload] = Field(default_factory=list)
    frame_ref: FrameReference
    review_status: ReviewStatus = Field(default=ReviewStatus.UNREVIEWED)
    review_note: str | None = None
    evidence_uri: str | None = None
    thumbnail_uri: str | None = None
    model_version: str | None = None
    config_version: str | None = None
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


class CameraMetadataMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION)
    message_type: MessageType = Field(default=MessageType.CAMERA_METADATA)
    camera_id: str
    trace_id: str | None = None
    timestamp: str | None = None
    detections: list[DetectionPayload] = Field(default_factory=list)
    incident: IncidentPayload | None = None
    review_status: ReviewStatus = Field(default=ReviewStatus.UNREVIEWED)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HistoryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    camera_id: str
    organization_id: str = "default-org"
    store_id: str = "main-store"
    trace_id: str
    timestamp: str
    label: str
    confidence: float
    severity: Severity
    event_type: str
    review_status: ReviewStatus = Field(default=ReviewStatus.UNREVIEWED)
    review_note: str | None = None
    evidence_uri: str | None = None
    thumbnail_uri: str | None = None
    model_version: str | None = None
    config_version: str | None = None
    detections: list[DetectionPayload] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
