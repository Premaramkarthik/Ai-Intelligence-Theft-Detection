"""
MediaBridge main — camera supervisor.
Entry: python -m services.mediabridge.main
"""
from __future__ import annotations

import asyncio
import os
import signal

import redis.asyncio as aioredis
from prometheus_client import start_http_server

from shared.logging.logger import get_logger
from services.mediabridge.services.camera_worker import CameraWorker
from services.mediabridge.utils.metrics import METRICS_PORT

from shared.core.settings import get_settings

log = get_logger(__name__)

cfg = get_settings()
REDIS_URL = cfg.redis_url
CAMERA_SOURCES = cfg.camera_sources.split(",")  # webcam indices or RTSP URLs


async def run() -> None:
    shutdown_event = asyncio.Event()
    active_workers: dict[str, tuple[CameraWorker, asyncio.Task]] = {}

    def _handle_signal() -> None:
        log.info("SIGTERM — shutting down mediabridge")
        shutdown_event.set()
        for worker, task in active_workers.values():
            task.cancel()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    start_http_server(METRICS_PORT)
    log.info("Prometheus metrics", extra={"port": METRICS_PORT})

    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    CAMERA_SOURCES_KEY = "camera_sources"

    # Initial seeding from settings if Redis is empty and sources are defined
    existing = await redis.hgetall(CAMERA_SOURCES_KEY)
    if not existing and cfg.camera_sources.strip():
        # Clean the sources list
        sources_list = [s.strip() for s in cfg.camera_sources.split(",") if s.strip()]
        for i, src in enumerate(sources_list):
            cam_id = f"cam{i+1:02d}"
            await redis.hset(CAMERA_SOURCES_KEY, cam_id, src)
            log.info("Seeded initial camera", extra={"id": cam_id, "src": src})
            
            # Also seed default config for the camera
            config_key = f"config:{cam_id}"
            if not await redis.exists(config_key):
                await redis.hset(config_key, mapping={
                    "roi": "{}",
                    "confidence_threshold": "0.5",
                    "iou_threshold": "0.15",
                    "hand_dist_px": "80",
                    "enabled": "true"
                })
                log.info("Seeded default config", extra={"id": cam_id})

    log.info("Starting camera supervisor loop")
    
    try:
        while not shutdown_event.is_set():
            # 1. Sync Redis with active workers
            sources = await redis.hgetall(CAMERA_SOURCES_KEY)
            
            # Start new workers
            for cam_id, src in sources.items():
                if cam_id not in active_workers:
                    log.info("Starting new camera worker", extra={"id": cam_id, "src": src})
                    worker = CameraWorker(src, redis, shutdown_event, camera_id=cam_id)
                    task = asyncio.create_task(worker.run())
                    active_workers[cam_id] = (worker, task)
            
            # Monitor health & Stop removed workers
            to_remove = []
            for cam_id, (worker, task) in active_workers.items():
                if cam_id not in sources:
                    log.info("Stopping camera worker (Source removed)", extra={"id": cam_id})
                    task.cancel()
                    to_remove.append(cam_id)
                elif task.done():
                    # Worker crashed or finished unexpectedly
                    try:
                        exc = task.exception()
                        log.error("Camera worker crashed", extra={"id": cam_id, "error": str(exc)})
                    except Exception:
                        log.warning("Camera worker stopped unexpectedly", extra={"id": cam_id})
                    
                    # Restart after delay
                    log.info("Restarting camera worker", extra={"id": cam_id})
                    new_worker = CameraWorker(sources[cam_id], redis, shutdown_event, camera_id=cam_id)
                    new_task = asyncio.create_task(new_worker.run())
                    active_workers[cam_id] = (new_worker, new_task)
            
            for cid in to_remove:
                del active_workers[cid]
                
            # Wait or check shutdown event
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=5.0) # More frequent polling for production
            except asyncio.TimeoutError:
                continue

    finally:
        # Cleanup
        for cam_id, (worker, task) in active_workers.items():
            task.cancel()
        
        await redis.aclose()
        log.info("MediaBridge stopped")


if __name__ == "__main__":
    asyncio.run(run())
