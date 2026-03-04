"""GET /api/events — returns recent detection events."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from services.signaling.api.deps import verify_jwt
from shared.logging.logger import get_logger

router = APIRouter()
log = get_logger(__name__)


@router.get("/events")
async def get_recent_events(request: Request, limit: int = 50) -> list[dict]:
    """Returns the latest detection events from the database."""
    db = request.app.state.db
    pool = db.get_pool()

    query = "SELECT camera_id, trace_id, class_name, confidence, created_at FROM detection_events ORDER BY created_at DESC LIMIT $1"
    rows = await pool.fetch(query, limit)

    return [
        {
            "camera_id": row["camera_id"],
            "trace_id": row["trace_id"],
            "label": row["class_name"],
            "confidence": row["confidence"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]
