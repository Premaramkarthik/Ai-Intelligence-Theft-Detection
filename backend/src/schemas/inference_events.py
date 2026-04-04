from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InferenceKafkaEventPayload(BaseModel):
    event: str = "inference.updated"
    emitted_at: datetime = Field(default_factory=_utc_now)
    camera_id: str
    stream_name: str
    persistent_id: str
    local_track_id: str
    strategy: str
    score: float
    alert_level: str  # "normal" | "warning" | "alert"
    label: str
    model_name: str
    sampled_at: datetime


class InferenceStateResponse(BaseModel):
    enabled: bool
    strategy: str | None = None  # "cnn_transformer" | "vjepa_probe"
    available_strategies: list[str] = Field(default_factory=list)
    healthy: bool = True
    last_error_message: str | None = None
    queue_depth: int = 0
    active_tracks: int = 0
    last_result_at: datetime | None = None
