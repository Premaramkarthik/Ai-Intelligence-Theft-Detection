"""Manual alert trigger endpoint."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from services.signaling.api.deps import verify_jwt
from shared.redis.keys import INCIDENT_STREAM_KEY, incident_channel
from shared.tracing import new_trace_id
from shared.types.events import IncidentEvent, FrameReference, Severity, utc_now_iso

router = APIRouter()


class AlertTrigger(BaseModel):
    label: str
    confidence: float
    camera_id: str = "manual"


@router.post("/trigger")
async def trigger_alert(
    request: Request,
    data: AlertTrigger,
    _user: str = Depends(verify_jwt),
) -> dict:
    redis = request.app.state.redis
    event = IncidentEvent(
        camera_id=data.camera_id,
        trace_id=new_trace_id(),
        timestamp=utc_now_iso(),
        label=data.label,
        confidence=data.confidence,
        severity=Severity.HIGH,
        frame_ref=FrameReference(camera_id=data.camera_id, slot_id=0, generation=0),
        metadata={"source": "manual_trigger"},
    )
    payload = event.model_dump(mode="json")
    serialized = json.dumps(payload)
    await redis.xadd(INCIDENT_STREAM_KEY, {"payload": serialized})
    await redis.publish(incident_channel(data.camera_id), serialized)
    return {"status": "success", "message": "Alert triggered", "payload": payload}
