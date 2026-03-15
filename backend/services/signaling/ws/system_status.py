"""WS /ws/status — streams system hardware metrics with cached GPU stats."""
from __future__ import annotations

import asyncio
import time

import psutil
import redis.asyncio as aioredis

try:
    import pynvml
    HAS_NVML = True
except ImportError:
    HAS_NVML = False

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from services.signaling.api.deps import verify_ws_token
from services.signaling.utils.metrics import websocket_clients
from shared.logging.logger import get_logger
from shared.redis.keys import CAMERA_SOURCES_KEY, frame_pointer_key
from shared.types.status import GpuStatus, SystemResourceStatus, SystemStatusMessage

router = APIRouter()
log = get_logger(__name__)

GPU_CACHE_TTL = 5.0  # Cache GPU stats for 5s


def _get_gpu_stats() -> dict:
    """Query GPU via NVML. Called from thread to avoid blocking event loop."""
    stats: dict = {"available": HAS_NVML}
    if not HAS_NVML:
        return stats
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        stats.update({
            "total": info.total // 1024**2,
            "used": info.used // 1024**2,
            "free": info.free // 1024**2,
            "utilization": pynvml.nvmlDeviceGetUtilizationRates(handle).gpu,
            "temperature": pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU),
        })
        pynvml.nvmlShutdown()
    except Exception:
        stats["error"] = "Could not query NVIDIA GPU"
    return stats


@router.websocket("/ws/status")
async def ws_status(websocket: WebSocket) -> None:
    try:
        verify_ws_token(websocket)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    websocket_clients.labels(channel="status").inc()
    log.info("System Status WS connected")

    gpu_cache: dict = {}
    gpu_cache_ts: float = 0.0

    try:
        while True:
            now = time.time()

            # Refresh GPU stats only every GPU_CACHE_TTL seconds
            if now - gpu_cache_ts > GPU_CACHE_TTL:
                gpu_cache = await asyncio.to_thread(_get_gpu_stats)
                gpu_cache_ts = now

            redis_alive = False
            active_workers = 0
            total_cameras = 0
            redis_client: aioredis.Redis = websocket.app.state.redis
            try:
                await redis_client.ping()
                redis_alive = True
                cameras = await redis_client.hgetall(CAMERA_SOURCES_KEY)
                total_cameras = len(cameras)
                for camera_id in cameras:
                    if await redis_client.exists(frame_pointer_key(camera_id)):
                        active_workers += 1
            except Exception:
                redis_alive = False

            payload = SystemStatusMessage(
                status="healthy" if redis_alive and active_workers == total_cameras else "degraded",
                redis="connected" if redis_alive else "disconnected",
                cameras={
                    "total_configured": total_cameras,
                    "active_streaming": active_workers,
                },
                ts=now,
                gpu=GpuStatus.model_validate(gpu_cache),
                system=SystemResourceStatus(
                    cpu_usage=psutil.cpu_percent(),
                    ram_usage=psutil.virtual_memory().percent,
                ),
            )

            await websocket.send_text(payload.model_dump_json())
            await asyncio.sleep(1.0)

    except WebSocketDisconnect:
        log.info("System Status WS disconnected")
    except Exception as exc:
        log.error("System Status WS error", extra={"error": str(exc)})
    finally:
        websocket_clients.labels(channel="status").dec()
