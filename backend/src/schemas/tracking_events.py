from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TrackingKafkaTrackPayload(BaseModel):
    track_id: str
    persistent_id: str | None
    class_name: str | None
    confidence: float
    similarity: float | None
    left: int
    top: int
    width: int
    height: int
    sampled_at: datetime = Field(default_factory=_utc_now)
    age_frames: int = 0
    consecutive_hits: int = 0
    frames_since_update: int = 0
    persistent_id_state: str = "pending"  # "pending" | "assigned" | "local"


class TrackingKafkaEventPayload(BaseModel):
    event: str = "tracking.updated"
    emitted_at: datetime = Field(default_factory=_utc_now)
    camera_id: str
    stream_name: str
    annotated_stream_name: str
    active_tracks: int
    tracks: list[TrackingKafkaTrackPayload]
