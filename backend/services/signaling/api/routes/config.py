"""PUT/GET /api/config/{camera_id}"""
from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException

from services.signaling.api.deps import get_redis, verify_jwt
from services.signaling.schemas.camera import ROIConfigRequest, ROIConfigResponse
from shared.core.config import CameraConfig, camera_config_mapping, parse_camera_config
from shared.redis.keys import camera_config_key

router = APIRouter()


@router.put("/config/{camera_id}")
async def set_config(
    camera_id: str,
    body: ROIConfigRequest,
    _user: str = Depends(verify_jwt),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    config = CameraConfig(
        camera_id=camera_id,
        organization_id=body.organization_id,
        store_id=body.store_id,
        roi=body.roi or {},
        confidence_threshold=body.confidence_threshold,
        iou_threshold=body.iou_threshold,
        hand_dist_px=body.hand_dist_px,
        interaction_frames=body.interaction_frames,
        enabled=body.enabled,
    )
    await redis.hset(camera_config_key(camera_id), mapping=camera_config_mapping(config))
    return {"status": "ok", "camera_id": camera_id}


@router.get("/config/{camera_id}", response_model=ROIConfigResponse)
async def get_config(
    camera_id: str,
    _user: str = Depends(verify_jwt),
    redis: aioredis.Redis = Depends(get_redis),
) -> ROIConfigResponse:
    raw = await redis.hgetall(camera_config_key(camera_id))
    if not raw:
        raise HTTPException(status_code=404, detail="Camera config not found")
    config = parse_camera_config(camera_id, raw)
    return ROIConfigResponse(
        camera_id=camera_id,
        organization_id=config.organization_id,
        store_id=config.store_id,
        roi=config.roi,
        confidence_threshold=config.confidence_threshold,
        iou_threshold=config.iou_threshold,
        hand_dist_px=config.hand_dist_px,
        interaction_frames=config.interaction_frames,
        enabled=config.enabled,
    )
