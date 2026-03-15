"""
Inference service main — multi-GPU worker pool with Redis Stream frame queue.
Entry point: python -m services.inference.main

Supports spawning multiple GPU workers:
  INFERENCE_GPU_WORKERS=2 python -m services.inference.main
Each worker claims frames from the shared Redis list and processes independently.
"""
from __future__ import annotations

import asyncio
import os
import signal

import redis.asyncio as aioredis

from shared.redis.frame_queue import dequeue_fair_frame, frame_age_seconds, list_camera_queues
from shared.logging.logger import get_logger
from shared.runtime import RuntimeState, next_backoff_delay, start_runtime_server
from services.inference.ml.pipeline import InferencePipeline
from services.inference.utils.metrics import METRICS_PORT
from services.inference.utils.metrics import (
    camera_frame_age_seconds,
    camera_queue_depth,
    frames_dropped,
    queue_depth,
    redis_reconnects,
    stale_frame_drops,
)

from shared.core.settings import get_settings
from shared.redis.keys import frame_queue_key

log = get_logger(__name__)

cfg = get_settings()
REDIS_URL = cfg.redis_url
GPU_WORKERS = int(os.environ.get("INFERENCE_GPU_WORKERS", "1"))


async def _connect_redis(state: RuntimeState, attempt: int) -> aioredis.Redis:
    redis = aioredis.from_url(REDIS_URL, decode_responses=False)
    try:
        await redis.ping()
        state.dependency("redis", True, "connected")
        return redis
    except Exception as exc:
        await redis.aclose()
        state.dependency("redis", False, str(exc))
        state.set_degraded(True)
        raise


async def _inference_worker(
    worker_id: int,
    redis: aioredis.Redis,
    shutdown_event: asyncio.Event,
) -> None:
    """Single inference worker — claims frames from shared queue."""
    pipeline = InferencePipeline()
    await pipeline.load_models()
    log.info(f"GPU Worker {worker_id} ready")
    camera_ids: list[str] = []
    rr_index = 0
    refresh_at = 0.0

    while not shutdown_event.is_set():
        now = __import__("time").time()
        if now >= refresh_at:
            camera_ids = await list_camera_queues(redis)
            refresh_at = now + 2.0
            for camera_id in camera_ids:
                camera_queue_depth.labels(camera_id=camera_id).set(await redis.llen(frame_queue_key(camera_id)))
            queue_depth.set(sum(await asyncio.gather(*(redis.llen(frame_queue_key(camera_id)) for camera_id in camera_ids))) if camera_ids else 0)

        item = await dequeue_fair_frame(redis, camera_ids, start_index=rr_index)
        if item is None:
            continue
        camera_id, payload, rr_index = item
        age = frame_age_seconds(payload)
        camera_frame_age_seconds.labels(camera_id=camera_id).set(age)
        if age > cfg.frame_stale_after_s:
            stale_frame_drops.labels(camera_id=camera_id).inc()
            frames_dropped.inc()
            continue
        await pipeline.process(payload, redis)


async def run() -> None:
    shutdown_event = asyncio.Event()
    state = RuntimeState(service_name="inference")
    runner, _site = await start_runtime_server(state, host=cfg.metrics_bind_host, port=METRICS_PORT)
    state.set_booted(True)

    def _handle_signal() -> None:
        log.info("SIGTERM — shutting down inference")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            signal.signal(sig, lambda _signum, _frame: _handle_signal())

    log.info("Inference runtime server", extra={"port": METRICS_PORT, "host": cfg.metrics_bind_host})

    if GPU_WORKERS > 1:
        redis: aioredis.Redis | None = None
        try:
            attempt = 0
            pipeline = InferencePipeline()
            await pipeline.load_models()
            state.update_detail(**pipeline.readiness_snapshot(), gpu_workers=GPU_WORKERS)
            while not shutdown_event.is_set():
                try:
                    redis = await _connect_redis(state, attempt)
                    state.set_ready(True)
                    workers = [
                        asyncio.create_task(_inference_worker(i, redis, shutdown_event))
                        for i in range(GPU_WORKERS)
                    ]
                    log.info(f"Starting {GPU_WORKERS} GPU inference workers")
                    await asyncio.gather(*workers)
                except Exception as exc:
                    delay = next_backoff_delay(attempt)
                    redis_reconnects.inc()
                    state.set_degraded(True)
                    log.warning("Inference degraded; retrying Redis", extra={"error": str(exc), "delay": delay})
                    if redis is not None:
                        await redis.aclose()
                        redis = None
                    await asyncio.sleep(delay)
                    attempt += 1
        finally:
            from shared.shm.ring_buffer import ReaderCache
            ReaderCache.clear()
            if redis is not None:
                await redis.aclose()
            await runner.cleanup()
            log.info("Inference service stopped")
    else:
        # Single worker (original path)
        pipeline = InferencePipeline()
        await pipeline.load_models()
        state.update_detail(**pipeline.readiness_snapshot(), gpu_workers=1)
        try:
            redis: aioredis.Redis | None = None
            attempt = 0
            while not shutdown_event.is_set():
                try:
                    if redis is None:
                        redis = await _connect_redis(state, attempt)
                        state.set_ready(True)
                        attempt = 0
                        log.info("Inference service ready (single worker)")
                    camera_ids = await list_camera_queues(redis)
                    depths = []
                    for camera_id in camera_ids:
                        depth = await redis.llen(frame_queue_key(camera_id))
                        depths.append(depth)
                        camera_queue_depth.labels(camera_id=camera_id).set(depth)
                    queue_depth.set(sum(depths))
                    item = await dequeue_fair_frame(redis, camera_ids, start_index=int(state.details.get("rr_index", 0)))
                    if item is None:
                        continue
                    camera_id, payload, next_index = item
                    state.update_detail(rr_index=next_index)
                    age = frame_age_seconds(payload)
                    camera_frame_age_seconds.labels(camera_id=camera_id).set(age)
                    if age > cfg.frame_stale_after_s:
                        stale_frame_drops.labels(camera_id=camera_id).inc()
                        frames_dropped.inc()
                        continue
                    await pipeline.process(payload, redis)
                except Exception as exc:
                    delay = next_backoff_delay(attempt)
                    redis_reconnects.inc()
                    state.set_degraded(True)
                    state.dependency("redis", False, str(exc))
                    if redis is not None:
                        await redis.aclose()
                        redis = None
                    log.warning("Inference loop degraded; retrying", extra={"error": str(exc), "delay": delay})
                    await asyncio.sleep(delay)
                    attempt += 1
        finally:
            from shared.shm.ring_buffer import ReaderCache
            ReaderCache.clear()
            if redis is not None:
                await redis.aclose()
            await runner.cleanup()
            log.info("Inference service stopped")


if __name__ == "__main__":
    asyncio.run(run())
