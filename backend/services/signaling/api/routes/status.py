from fastapi import APIRouter, Depends
import redis.asyncio as aioredis
import time
import psutil
try:
    import pynvml
    HAS_NVML = True
except ImportError:
    HAS_NVML = False

from services.signaling.api.deps import get_redis, verify_jwt
from shared.logging.logger import get_logger
from shared.redis.keys import CAMERA_SOURCES_KEY, frame_pointer_key
from shared.types.status import CameraFleetStatus, GpuStatus, SystemResourceStatus, SystemStatusMessage

router = APIRouter()
log = get_logger(__name__)

@router.get("/status")
async def get_system_status(_user: str = Depends(verify_jwt), redis: aioredis.Redis = Depends(get_redis)):
    """Comprehensive health check for the entire pipeline."""
    
    # 1. Redis Check
    redis_alive = False
    try:
        await redis.ping()
        redis_alive = True
    except Exception:
        pass

    # 2. Camera Stats
    cameras = await redis.hgetall(CAMERA_SOURCES_KEY)
    active_workers = 0
    for cam_id in cameras:
        if await redis.exists(frame_pointer_key(cam_id)):
            active_workers += 1

    # 3. GPU Stats (Simple)
    gpu_stats = {"available": HAS_NVML}
    if HAS_NVML:
        try:
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpu_stats.update({
                "total": info.total // 1024**2,
                "used": info.used // 1024**2,
                "free": info.free // 1024**2,
                "utilization": pynvml.nvmlDeviceGetUtilizationRates(handle).gpu,
                "temperature": pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU),
            })
            pynvml.nvmlShutdown()
        except Exception:
            gpu_stats["error"] = "Could not query NVIDIA GPU"

    # 4. CPU/RAM
    system_stats = {
        "cpu_usage": psutil.cpu_percent(),
        "ram_usage": psutil.virtual_memory().percent
    }

    payload = SystemStatusMessage(
        status="healthy" if redis_alive and active_workers == len(cameras) else "degraded",
        redis="connected" if redis_alive else "disconnected",
        cameras=CameraFleetStatus(
            total_configured=len(cameras),
            active_streaming=active_workers,
        ),
        gpu=GpuStatus.model_validate(gpu_stats),
        system=SystemResourceStatus.model_validate(system_stats),
        uptime=time.time(),
    )
    return payload.model_dump(mode="json")
