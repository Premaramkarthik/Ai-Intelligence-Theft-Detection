"""GET /api/camera/{camera_id}/snapshot — returns JPEG frame."""
from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from services.signaling.api.deps import get_redis, verify_jwt
from services.signaling.services.camera_service import grab_jpeg

router = APIRouter()


@router.get(
    "/camera/{camera_id}/snapshot",
    response_class=Response,
)
async def snapshot(
    camera_id: str,
    redis: aioredis.Redis = Depends(get_redis),
) -> Response:
    jpeg = await grab_jpeg(redis, camera_id)
    if jpeg is None:
        raise HTTPException(status_code=503, detail="No frame available")
    return Response(content=jpeg, media_type="image/jpeg")
