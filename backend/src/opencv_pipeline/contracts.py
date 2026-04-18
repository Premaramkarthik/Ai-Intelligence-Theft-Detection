"""Shared contracts for the modular OpenCV edge pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class DropPolicy(str, Enum):
    """Backpressure behavior for bounded buffers."""

    drop_oldest = "drop_oldest"
    drop_newest = "drop_newest"
    block = "block"


class TrackIdentityState(str, Enum):
    """Identity assignment state for one track."""

    pending = "pending"
    assigned = "assigned"
    merged = "merged"
    expired = "expired"


class IdentityEventType(str, Enum):
    """Lifecycle transitions for persistent identities."""

    created = "identity.created"
    updated = "identity.updated"
    merged = "identity.merged"
    expired = "identity.expired"


@dataclass(slots=True, frozen=True)
class FrameSourceConfig:
    """Configuration for one camera/video source."""

    camera_id: str
    stream_name: str
    source_uri: str | int
    api_preference: int = 0
    target_width: int = 1280
    target_height: int = 720
    target_fps: float = 10.0
    calibration_path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FramePacket:
    """One captured frame with timing and source metadata."""

    camera_id: str
    stream_name: str
    sequence_number: int
    captured_at: datetime
    monotonic_ns: int
    frame_bgr: np.ndarray
    width: int
    height: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SynchronizedFrameBundle:
    """Tuple of camera frames aligned within the configured tolerance."""

    bundle_id: int
    emitted_at: datetime
    packets: list[FramePacket]
    span_ms: float


@dataclass(slots=True)
class CalibrationProfile:
    """Intrinsic/extrinsic camera calibration data."""

    camera_id: str
    camera_matrix: np.ndarray | None = None
    distortion_coefficients: np.ndarray | None = None
    homography: np.ndarray | None = None
    rotation_matrix: np.ndarray | None = None
    translation_vector: np.ndarray | None = None


@dataclass(slots=True)
class ProcessedFrame:
    """Frame state after preprocessing and calibration."""

    packet: FramePacket
    calibration: CalibrationProfile | None
    raw_bgr: np.ndarray
    working_bgr: np.ndarray
    rgb: np.ndarray
    normalized_rgb: np.ndarray
    gray: np.ndarray
    low_light: bool
    world_reference_frame: np.ndarray | None = None


@dataclass(slots=True)
class MotionSummary:
    """Motion estimates derived from optical flow and foreground masks."""

    mean_magnitude: float = 0.0
    dominant_dx: float = 0.0
    dominant_dy: float = 0.0
    foreground_ratio: float = 0.0
    is_motion_consistent: bool = True


@dataclass(slots=True, frozen=True)
class Detection:
    """One detector output in left-top-width-height format."""

    left: int
    top: int
    width: int
    height: int
    confidence: float
    class_id: int
    class_name: str


@dataclass(slots=True)
class TrackedObject:
    """One tracked object enriched with identity state."""

    camera_id: str
    stream_name: str
    track_id: str
    left: int
    top: int
    width: int
    height: int
    confidence: float
    class_name: str = "person"
    age_frames: int = 0
    consecutive_hits: int = 0
    frames_since_update: int = 0
    persistent_id: str | None = None
    persistent_id_state: TrackIdentityState = TrackIdentityState.pending
    similarity: float | None = None
    embedding: np.ndarray | None = None
    world_x: float | None = None
    world_y: float | None = None


@dataclass(slots=True, frozen=True)
class IdentityLifecycleEvent:
    """One persistent identity lifecycle transition."""

    event_type: IdentityEventType
    camera_id: str
    stream_name: str
    local_track_id: str
    persistent_id: str
    previous_persistent_id: str | None
    matched_existing: bool
    similarity: float | None
    occurred_at: datetime
    left: int
    top: int
    width: int
    height: int
    world_x: float | None = None
    world_y: float | None = None


@dataclass(slots=True)
class PipelineOutput:
    """Final output for one processed camera frame."""

    processed_frame: ProcessedFrame
    annotated_bgr: np.ndarray
    motion: MotionSummary
    detections: list[Detection]
    tracks: list[TrackedObject]
    identity_events: list[IdentityLifecycleEvent]
    pipeline_latency_ms: float
    detection_latency_ms: float
    tracking_latency_ms: float
    reid_latency_ms: float
    identity_latency_ms: float
