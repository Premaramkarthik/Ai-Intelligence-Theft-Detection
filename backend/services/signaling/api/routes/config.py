"""PUT/GET /api/config/{camera_id}"""
from __future__ import annotations

import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException

from services.signaling.api.deps import get_redis, verify_jwt
from services.signaling.schemas.camera import ROIConfigRequest, ROIConfigResponse

router = APIRouter()


@router.put("/config/{camera_id}")
async def set_config(
    camera_id: str,
    body: ROIConfigRequest,
    _user: str = Depends(verify_jwt),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    data = {
        "roi": json.dumps(body.roi or {}),
        "confidence_threshold": str(body.confidence_threshold),
        "iou_threshold": str(body.iou_threshold),
        "hand_dist_px": str(body.hand_dist_px),
        "enabled": str(body.enabled).lower(),
    }
    await redis.hset(f"config:{camera_id}", mapping=data)
    return {"status": "ok", "camera_id": camera_id}


@router.get("/config/{camera_id}", response_model=ROIConfigResponse)
async def get_config(
    camera_id: str,
    _user: str = Depends(verify_jwt),
    redis: aioredis.Redis = Depends(get_redis),
) -> ROIConfigResponse:
    raw = await redis.hgetall(f"config:{camera_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Camera config not found")
    return ROIConfigResponse(
        camera_id=camera_id,
        roi=json.loads(raw.get("roi", "{}")),
        confidence_threshold=float(raw.get("confidence_threshold", 0.45)),
        iou_threshold=float(raw.get("iou_threshold", 0.15)),
        hand_dist_px=int(raw.get("hand_dist_px", 80)),
        enabled=raw.get("enabled", "true") == "true",
    )
