from fastapi import APIRouter, Depends
import redis.asyncio as aioredis
from services.signaling.api.deps import get_redis, verify_jwt
from shared.logging.logger import get_logger

router = APIRouter()
log = get_logger(__name__)

CAMERA_SOURCES_KEY = "camera_sources"

@router.get("/")
async def list_cameras(_user: str = Depends(verify_jwt), redis: aioredis.Redis = Depends(get_redis)):
    """List all configured camera sources."""
    sources = await redis.hgetall(CAMERA_SOURCES_KEY)
    return sources

@router.delete("/{camera_id}")
async def remove_camera(camera_id: str, _user: str = Depends(verify_jwt), redis: aioredis.Redis = Depends(get_redis)):
    """Remove a camera source and its configuration."""
    await redis.hdel(CAMERA_SOURCES_KEY, camera_id)
    # Also cleanup config and tracking state if needed
    await redis.delete(f"config:{camera_id}")
    await redis.delete(f"frame_ptr:{camera_id}")
    log.info("Camera removed", extra={"id": camera_id})
    return {"status": "ok"}
