from fastapi import APIRouter, Depends
import redis.asyncio as aioredis
import time
import psutil
try:
    import pynvml
    HAS_NVML = True
except ImportError:
    HAS_NVML = False

from services.signaling.api.deps import get_redis
from shared.logging.logger import get_logger

router = APIRouter()
log = get_logger(__name__)

@router.get("/status")
async def get_system_status(redis: aioredis.Redis = Depends(get_redis)):
    """Comprehensive health check for the entire pipeline."""
    
    # 1. Redis Check
    redis_alive = False
    try:
        await redis.ping()
        redis_alive = True
    except Exception:
        pass

    # 2. Camera Stats
    cameras = await redis.hgetall("camera_sources")
    active_workers = 0
    for cam_id in cameras:
        if await redis.exists(f"frame_ptr:{cam_id}"):
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
                "utilization": pynvml.nvmlDeviceGetUtilizationRates(handle).gpu
            })
            pynvml.nvmlShutdown()
        except Exception:
            gpu_stats["error"] = "Could not query NVIDIA GPU"

    # 4. CPU/RAM
    system_stats = {
        "cpu_usage": psutil.cpu_percent(),
        "ram_usage": psutil.virtual_memory().percent
    }

    return {
        "status": "healthy" if redis_alive else "degraded",
        "redis": "connected" if redis_alive else "disconnected",
        "cameras": {
            "total_configured": len(cameras),
            "active_streaming": active_workers
        },
        "gpu": gpu_stats,
        "system": system_stats,
        "uptime": time.time() # Placeholder for real uptime
    }
