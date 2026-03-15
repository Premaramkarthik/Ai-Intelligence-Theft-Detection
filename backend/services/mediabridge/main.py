"""
MediaBridge main — camera supervisor.
Entry: python -m services.mediabridge.main
"""
from __future__ import annotations

import asyncio
import os
import signal

import redis.asyncio as aioredis

from shared.logging.logger import get_logger
from shared.redis.keys import CAMERA_SOURCES_KEY, FRAME_POINTER_PATTERN, FRAME_QUEUE_PATTERN, frame_queue_key
from shared.runtime import RuntimeState, next_backoff_delay, start_runtime_server
from services.mediabridge.services.camera_worker import CameraWorker
from services.mediabridge.utils.metrics import METRICS_PORT, frame_queue_depth, redis_reconnects

from shared.core.settings import get_settings

log = get_logger(__name__)

cfg = get_settings()
REDIS_URL = cfg.redis_url


async def _connect_redis(state: RuntimeState) -> aioredis.Redis:
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await redis.ping()
        state.dependency("redis", True, "connected")
        return redis
    except Exception as exc:
        await redis.aclose()
        state.dependency("redis", False, str(exc))
        state.set_degraded(True)
        raise


async def run() -> None:
    shutdown_event = asyncio.Event()
    active_workers: dict[str, tuple[CameraWorker, asyncio.Task]] = {}
    state = RuntimeState(service_name="mediabridge")
    runner, _site = await start_runtime_server(state, host=cfg.metrics_bind_host, port=METRICS_PORT)
    state.set_booted(True)

    def _handle_signal() -> None:
        log.info("SIGTERM — shutting down mediabridge")
        shutdown_event.set()
        for worker, task in active_workers.values():
            task.cancel()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            signal.signal(sig, lambda _signum, _frame: _handle_signal())

    log.info("MediaBridge runtime server", extra={"port": METRICS_PORT, "host": cfg.metrics_bind_host})
    
    try:
        redis: aioredis.Redis | None = None
        attempt = 0
        while not shutdown_event.is_set():
            try:
                if redis is None:
                    redis = await _connect_redis(state)
                    stale_keys = await redis.keys(FRAME_POINTER_PATTERN)
                    stale_frame_queues = await redis.keys(FRAME_QUEUE_PATTERN)
                    keys_to_delete = [frame_queue_key(), *stale_frame_queues, *stale_keys]
                    if keys_to_delete:
                        await redis.delete(*keys_to_delete)
                    state.update_detail(worker_manager_initialized=True)
                    state.set_ready(True)
                    attempt = 0
                    log.info("Starting camera supervisor loop")

                sources = await redis.hgetall(CAMERA_SOURCES_KEY)
                frame_queue_depth.set(await redis.llen(frame_queue_key()))

                for cam_id, src in sources.items():
                    if cam_id not in active_workers:
                        log.info("Starting new camera worker", extra={"id": cam_id, "src": src})
                        worker = CameraWorker(src, redis, shutdown_event, camera_id=cam_id)
                        task = asyncio.create_task(worker.run())
                        active_workers[cam_id] = (worker, task)

                to_remove = []
                for cam_id, (_worker, task) in active_workers.items():
                    if cam_id not in sources:
                        log.info("Stopping camera worker (Source removed)", extra={"id": cam_id})
                        task.cancel()
                        to_remove.append(cam_id)
                    elif task.done():
                        try:
                            exc = task.exception()
                            log.error("Camera worker crashed", extra={"id": cam_id, "error": str(exc)})
                        except Exception:
                            log.warning("Camera worker stopped unexpectedly", extra={"id": cam_id})
                        log.info("Restarting camera worker", extra={"id": cam_id})
                        new_worker = CameraWorker(sources[cam_id], redis, shutdown_event, camera_id=cam_id)
                        new_task = asyncio.create_task(new_worker.run())
                        active_workers[cam_id] = (new_worker, new_task)

                for cid in to_remove:
                    del active_workers[cid]

                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue
            except Exception as exc:
                delay = next_backoff_delay(attempt)
                redis_reconnects.inc()
                state.set_degraded(True)
                state.dependency("redis", False, str(exc))
                log.warning("MediaBridge degraded; retrying", extra={"error": str(exc), "delay": delay})
                if redis is not None:
                    await redis.aclose()
                    redis = None
                await asyncio.sleep(delay)
                attempt += 1

    finally:
        # Cleanup
        for cam_id, (_worker, task) in active_workers.items():
            task.cancel()
        if 'redis' in locals() and redis is not None:
            await redis.aclose()
        await runner.cleanup()
        log.info("MediaBridge stopped")


if __name__ == "__main__":
    asyncio.run(run())
