"""POST /api/alerts/trigger — manually trigger an alert."""
from __future__ import annotations

import json
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from services.signaling.api.deps import verify_jwt

router = APIRouter()

class AlertTrigger(BaseModel):
    label: str
    confidence: float
    camera_id: str = "manual"

@router.post("/trigger")
async def trigger_alert(request: Request, data: AlertTrigger, _user: str = Depends(verify_jwt)) -> dict:
    """Manually publishes a prediction to Redis to trigger the alerting service."""
    redis = request.app.state.redis
    
    payload = {
        "camera_id": data.camera_id,
        "label": data.label,
        "confidence": data.confidence,
        "ts": 0 # Simulation timestamp
    }
    
    await redis.publish("predictions", json.dumps(payload))
    
    return {"status": "success", "message": "Alert triggered", "payload": payload}
