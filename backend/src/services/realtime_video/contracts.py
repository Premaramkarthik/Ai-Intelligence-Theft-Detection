"""Contracts for the MediaMTX-backed real-time video pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic_ns
from typing import Any


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def monotonic_now_ns() -> int:
    """Return a monotonic timestamp in nanoseconds for worker-side timing."""

    return monotonic_ns()


@dataclass(slots=True)
class MediaMtxStreamEndpoints:
    """Public and internal endpoints for a stream routed through MediaMTX."""

    stream_name: str
    rtsp_pull_url: str
    hls_url: str
    whep_url: str


@dataclass(slots=True)
class FrameSample:
    """A sampled decoded frame and the metadata required by downstream consumers."""

    camera_id: str
    stream_name: str
    sequence_number: int
    sampled_at: datetime = field(default_factory=utc_now)
    sampled_monotonic_ns: int = field(default_factory=monotonic_now_ns)
    source_timestamp_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    pixel_format: str | None = None
    frame_array: Any = None


@dataclass(slots=True)
class StreamWorkerMetrics:
    """Operational counters for a single PyAV stream worker."""

    reconnect_attempts: int = 0
    decoded_frames: int = 0
    sampled_frames: int = 0
    dropped_frames: int = 0
    last_frame_at: datetime | None = None
    last_frame_monotonic_ns: int | None = None
    current_fps: float = 0.0
    queue_latency_ms: float = 0.0
    decode_time_ms: float = 0.0
    last_error: str | None = None


@dataclass(slots=True)
class StreamWorkerConfig:
    """Immutable configuration required by a single PyAV stream worker."""

    camera_id: str
    stream_name: str
    mediamtx_rtsp_url: str
    sample_fps: float = 5.0
    rtsp_transport: str = "tcp"
    open_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 5.0
    max_queue_wait_seconds: float = 0.25
    max_reconnect_attempts: int = 8


@dataclass(slots=True)
class TrackingTrackSnapshot:
    """Frontend-safe summary of one tracked person."""

    track_id: str
    persistent_id: str | None
    class_name: str | None
    confidence: float
    similarity: float | None
    left: int
    top: int
    width: int
    height: int


@dataclass(slots=True)
class TrackingWorkerMetrics:
    """Operational counters for a single tracking worker."""

    reconnect_attempts: int = 0
    processed_frames: int = 0
    published_frames: int = 0
    active_tracks: int = 0
    last_frame_at: datetime | None = None
    last_error: str | None = None
    tracks: list[TrackingTrackSnapshot] = field(default_factory=list)


@dataclass(slots=True)
class TrackingWorkerConfig:
    """Immutable configuration required by a single tracking worker."""

    camera_id: str
    source_stream_name: str
    annotated_stream_name: str
    source_rtsp_url: str
    annotated_publish_rtsp_url: str
    ffmpeg_binary: str
    sample_fps: float = 5.0
    output_fps: float = 5.0
    embedder_name: str = "mobilenet"
    tracker_lost_track_buffer: int = 30
    tracker_activation_threshold: float = 0.7
    tracker_minimum_consecutive_frames: int = 2
    tracker_minimum_iou_threshold: float = 0.1
    tracker_high_conf_det_threshold: float = 0.6
    identity_sync_interval_seconds: float = 1.0
    publish_update_interval_seconds: float = 0.5
    rtsp_transport: str = "tcp"
    open_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 5.0
    max_reconnect_attempts: int = 8
