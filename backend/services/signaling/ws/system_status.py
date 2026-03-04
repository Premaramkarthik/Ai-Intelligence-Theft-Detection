"""WS /ws/status — streams system hardware metrics with cached GPU stats."""
from __future__ import annotations

import asyncio
import json
import time

import psutil

try:
    import pynvml
    HAS_NVML = True
except ImportError:
    HAS_NVML = False

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from shared.logging.logger import get_logger

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
        })
        pynvml.nvmlShutdown()
    except Exception:
        stats["error"] = "Could not query NVIDIA GPU"
    return stats


@router.websocket("/ws/status")
async def ws_status(websocket: WebSocket) -> None:
    await websocket.accept()
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

            payload = {
                "ts": now,
                "system": {
                    "cpu_usage": psutil.cpu_percent(),
                    "ram_usage": psutil.virtual_memory().percent,
                },
                "gpu": gpu_cache,
            }

            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(1.0)

    except WebSocketDisconnect:
        log.info("System Status WS disconnected")
    except Exception as exc:
        log.error("System Status WS error", extra={"error": str(exc)})
