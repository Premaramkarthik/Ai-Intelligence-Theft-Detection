"""GET /api/events - returns recent incident events."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request

from services.signaling.api.deps import verify_jwt
from shared.types.events import HistoryEvent

router = APIRouter()


@router.get("/events")
async def get_recent_events(
    request: Request,
    limit: int = 50,
    _user: str = Depends(verify_jwt),
) -> list[dict]:
    db = request.app.state.db
    pool = db.get_pool()

    query = """
    SELECT event_id, camera_id, trace_id, event_type, class_name, confidence, severity, created_at, detections, metadata
    FROM detection_events
    ORDER BY created_at DESC
    LIMIT $1
    """
    rows = await pool.fetch(query, limit)

    response: list[dict] = []
    for row in rows:
        history_event = HistoryEvent(
            event_id=row["event_id"],
            camera_id=row["camera_id"],
            trace_id=row["trace_id"],
            timestamp=row["created_at"].isoformat(),
            label=row["class_name"],
            confidence=row["confidence"],
            severity=row["severity"],
            event_type=row["event_type"],
            detections=_coerce_json_field(row["detections"], default=[]),
            metadata=_coerce_json_field(row["metadata"], default={}),
        )
        response.append(history_event.model_dump(mode="json"))
    return response


def _coerce_json_field(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value
