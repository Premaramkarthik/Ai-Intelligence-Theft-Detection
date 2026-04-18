"""Shared tracking contracts used across detectors, trackers, and workers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

import numpy as np


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True, frozen=True)
class PersonDetection:
    """A single person detection in left-top-width-height format."""

    left: float
    top: float
    width: float
    height: float
    confidence: float
    class_name: str = "person"


class PersonDetector(Protocol):
    """Protocol implemented by all person detectors used by tracking workers."""

    def detect(self, frame: np.ndarray) -> list[PersonDetection]:
        """Detect visible persons in a single BGR frame."""


@dataclass(slots=True, frozen=True)
class TrackingTrackSnapshot:
    """Serializable track snapshot shared across Kafka and websocket fanout."""

    track_id: str
    persistent_id: str | None
    class_name: str | None
    confidence: float
    similarity: float | None
    left: int
    top: int
    width: int
    height: int
    sampled_at: datetime = field(default_factory=_utc_now)
    age_frames: int = 0
    consecutive_hits: int = 0
    frames_since_update: int = 0
    persistent_id_state: str = "pending"
