from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import redis.asyncio as aioredis
from services.signaling.api.deps import get_redis
from shared.logging.logger import get_logger

router = APIRouter()
log = get_logger(__name__)

CAMERA_SOURCES_KEY = "camera_sources"

class CameraSource(BaseModel):
    id: str
    source: str # 0 (webcam) or rtsp://...

@router.get("/")
async def list_cameras(redis: aioredis.Redis = Depends(get_redis)):
    sources = await redis.hgetall(CAMERA_SOURCES_KEY)
    return sources

@router.post("/")
async def add_camera(camera: CameraSource, redis: aioredis.Redis = Depends(get_redis)):
    await redis.hset(CAMERA_SOURCES_KEY, camera.id, camera.source)
    log.info("Camera added", extra={"id": camera.id, "source": camera.source})
    return {"status": "ok"}

@router.delete("/{camera_id}")
async def remove_camera(camera_id: str, redis: aioredis.Redis = Depends(get_redis)):
    await redis.hdel(CAMERA_SOURCES_KEY, camera_id)
    log.info("Camera removed", extra={"id": camera_id})
    return {"status": "ok"}
