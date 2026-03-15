"""GET /api/events - returns recent incident events."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from services.signaling.api.deps import verify_jwt
from shared.types.events import HistoryEvent, ReviewStatus

router = APIRouter()


class ReviewUpdateRequest(BaseModel):
    review_status: ReviewStatus
    review_note: str | None = None


@router.get("/events", response_model=list[HistoryEvent])
async def get_recent_events(
    request: Request,
    limit: int = 50,
    store_id: str | None = None,
    _user: str = Depends(verify_jwt),
) -> list[HistoryEvent]:
    db = request.app.state.db
    pool = db.get_pool()

    if store_id:
        query = """
        SELECT event_id, organization_id, store_id, camera_id, trace_id, event_type, class_name, confidence, severity,
               created_at, detections, metadata, review_status, review_note, evidence_uri, thumbnail_uri, model_version, config_version
        FROM detection_events
        WHERE store_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """
        rows = await pool.fetch(query, store_id, limit)
    else:
        query = """
        SELECT event_id, organization_id, store_id, camera_id, trace_id, event_type, class_name, confidence, severity,
               created_at, detections, metadata, review_status, review_note, evidence_uri, thumbnail_uri, model_version, config_version
        FROM detection_events
        ORDER BY created_at DESC
        LIMIT $1
        """
        rows = await pool.fetch(query, limit)

    response: list[HistoryEvent] = []
    for row in rows:
        history_event = HistoryEvent(
            event_id=row["event_id"],
            organization_id=row["organization_id"],
            store_id=row["store_id"],
            camera_id=row["camera_id"],
            trace_id=row["trace_id"],
            timestamp=row["created_at"].isoformat(),
            label=row["class_name"],
            confidence=row["confidence"],
            severity=row["severity"],
            event_type=row["event_type"],
            review_status=row["review_status"],
            review_note=row["review_note"],
            evidence_uri=row["evidence_uri"],
            thumbnail_uri=row["thumbnail_uri"],
            model_version=row["model_version"],
            config_version=row["config_version"],
            detections=_coerce_json_field(row["detections"], default=[]),
            metadata=_coerce_json_field(row["metadata"], default={}),
        )
        response.append(history_event)
    return response


@router.patch("/events/{event_id}/review")
async def update_review(
    event_id: str,
    body: ReviewUpdateRequest,
    request: Request,
    _user: str = Depends(verify_jwt),
) -> dict:
    pool = request.app.state.db.get_pool()
    result = await pool.execute(
        """
        UPDATE detection_events
        SET review_status = $2, review_note = $3
        WHERE event_id = $1
        """,
        event_id,
        body.review_status.value,
        body.review_note,
    )
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="Event not found")
    return {"status": "ok", "event_id": event_id, "review_status": body.review_status.value}


@router.get("/events/{event_id}/evidence")
async def get_event_evidence(
    event_id: str,
    request: Request,
    _user: str = Depends(verify_jwt),
) -> FileResponse:
    pool = request.app.state.db.get_pool()
    row = await pool.fetchrow(
        "SELECT evidence_uri FROM detection_events WHERE event_id = $1 ORDER BY created_at DESC LIMIT 1",
        event_id,
    )
    if not row or not row["evidence_uri"]:
        raise HTTPException(status_code=404, detail="Evidence not found")
    path = Path(row["evidence_uri"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Evidence file missing")
    return FileResponse(path)


@router.get("/events/{event_id}/thumbnail")
async def get_event_thumbnail(
    event_id: str,
    request: Request,
    _user: str = Depends(verify_jwt),
) -> FileResponse:
    pool = request.app.state.db.get_pool()
    row = await pool.fetchrow(
        "SELECT thumbnail_uri, evidence_uri FROM detection_events WHERE event_id = $1 ORDER BY created_at DESC LIMIT 1",
        event_id,
    )
    if not row or not (row["thumbnail_uri"] or row["evidence_uri"]):
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    path = Path(row["thumbnail_uri"] or row["evidence_uri"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file missing")
    return FileResponse(path)


def _coerce_json_field(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value
