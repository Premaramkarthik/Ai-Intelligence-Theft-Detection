"""Internal contracts for the inference plane."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class InferenceIngressSample:
    """One enriched track crop queued for inference dispatch."""

    camera_id: str
    stream_name: str
    local_track_id: str
    persistent_id: str          # must be "assigned" before queuing
    sampled_at: datetime
    left: int
    top: int
    width: int
    height: int
    crop: Any                   # np.ndarray at runtime; typed as Any to avoid numpy import
    age_frames: int
    consecutive_hits: int
    frames_since_update: int
    persistent_id_state: str    # only "assigned" samples are dispatched


@dataclass(slots=True)
class InferenceSnapshot:
    """Per-camera inference state snapshot for REST / WS responses."""

    camera_id: str
    enabled: bool
    strategy: str | None = None
    healthy: bool = True
    last_error_message: str | None = None
    queue_depth: int = 0
    active_tracks: int = 0
    last_result_at: datetime | None = None


@dataclass(slots=True)
class InferenceWorkerConfig:
    """Immutable configuration for one camera's inference orchestrator."""

    camera_id: str
    strategy: str = "cnn_transformer"           # "cnn_transformer" | "vjepa_probe"
    triton_url: str = "localhost:8001"
    triton_max_in_flight: int = 8               # per-strategy bounded concurrency
    temporal_buffer_size: int = 16
    dispatch_min_consecutive_hits: int = 4
    dispatch_min_crop_width: int = 32
    dispatch_min_crop_height: int = 64
    identity_gap_reset_seconds: float = 2.0
    ingress_queue_maxsize: int = 64
    score_warning_threshold: float = 0.5
    score_alert_threshold: float = 0.8
    extra: dict[str, Any] = field(default_factory=dict)
