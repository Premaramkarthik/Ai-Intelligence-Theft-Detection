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
from prometheus_client import start_http_server

from shared.logging.logger import get_logger
from services.inference.ml.pipeline import InferencePipeline
from services.inference.utils.metrics import METRICS_PORT

from shared.core.settings import get_settings

log = get_logger(__name__)

cfg = get_settings()
REDIS_URL = cfg.redis_url
FRAME_QUEUE = "frames"
GPU_WORKERS = int(os.environ.get("INFERENCE_GPU_WORKERS", "1"))


async def _inference_worker(
    worker_id: int,
    redis: aioredis.Redis,
    shutdown_event: asyncio.Event,
) -> None:
    """Single inference worker — claims frames from shared queue."""
    pipeline = InferencePipeline()
    await pipeline.load_models()
    log.info(f"GPU Worker {worker_id} ready")

    while not shutdown_event.is_set():
        # Drain excess frames to prevent lag
        qlen = await redis.llen(FRAME_QUEUE)
        if qlen > 100:
            log.warning("Inference lagging, draining queue", extra={"worker": worker_id, "qlen": qlen})
            last_item = await redis.lindex(FRAME_QUEUE, -1)
            await redis.delete(FRAME_QUEUE)
            if last_item:
                await redis.rpush(FRAME_QUEUE, last_item)

        item = await redis.blpop(FRAME_QUEUE, timeout=1)
        if item is None:
            continue
        _, payload = item
        await pipeline.process(payload, redis)


async def run() -> None:
    shutdown_event = asyncio.Event()

    def _handle_signal() -> None:
        log.info("SIGTERM — shutting down inference")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    start_http_server(METRICS_PORT)
    log.info("Prometheus metrics", extra={"port": METRICS_PORT})

    redis = aioredis.from_url(REDIS_URL, decode_responses=False)

    if GPU_WORKERS > 1:
        log.info(f"Starting {GPU_WORKERS} GPU inference workers")
        workers = [
            asyncio.create_task(_inference_worker(i, redis, shutdown_event))
            for i in range(GPU_WORKERS)
        ]
        log.info("Inference service ready (multi-GPU)")
        try:
            await asyncio.gather(*workers)
        finally:
            from shared.shm.ring_buffer import ReaderCache
            ReaderCache.clear()
            await redis.aclose()
            log.info("Inference service stopped")
    else:
        # Single worker (original path)
        pipeline = InferencePipeline()
        await pipeline.load_models()
        log.info("Inference service ready (single worker)")
        try:
            while not shutdown_event.is_set():
                qlen = await redis.llen(FRAME_QUEUE)
                if qlen > 100:
                    log.warning("Inference lagging, draining queue", extra={"qlen": qlen})
                    last_item = await redis.lindex(FRAME_QUEUE, -1)
                    await redis.delete(FRAME_QUEUE)
                    if last_item:
                        await redis.rpush(FRAME_QUEUE, last_item)

                item = await redis.blpop(FRAME_QUEUE, timeout=1)
                if item is None:
                    continue
                _, payload = item
                await pipeline.process(payload, redis)
        finally:
            from shared.shm.ring_buffer import ReaderCache
            ReaderCache.clear()
            await redis.aclose()
            log.info("Inference service stopped")


if __name__ == "__main__":
    asyncio.run(run())
