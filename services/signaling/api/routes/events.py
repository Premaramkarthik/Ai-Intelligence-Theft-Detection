"""GET /api/events — returns recent detection events."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from shared.db.session import DatabaseSession
from services.signaling.api.deps import verify_jwt

router = APIRouter()
db = DatabaseSession()

@router.get("/events")
async def get_recent_events(limit: int = 50) -> list[dict]:
    """Returns the latest detection events from the database."""
    await db.connect()
    pool = db.get_pool()
    
    query = "SELECT camera_id, trace_id, label, confidence, created_at FROM detection_events ORDER BY created_at DESC LIMIT $1"
    rows = await pool.fetch(query, limit)
    
    return [
        {
            "camera_id": row["camera_id"],
            "trace_id": row["trace_id"],
            "label": row["label"],
            "confidence": row["confidence"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]
