"""
Inference service main — Redis consumer loop.
Entry point: python -m services.inference.main
"""
from __future__ import annotations

import asyncio
import os
import signal

import redis.asyncio as aioredis
from prometheus_client import start_http_server

from libs.shared.logging.logger import get_logger
from services.inference.ml.pipeline import InferencePipeline
from services.inference.utils.metrics import METRICS_PORT

from libs.shared.core.settings import get_settings

log = get_logger(__name__)

cfg = get_settings()
REDIS_URL = cfg.redis_url
FRAME_QUEUE = "frames"


async def run() -> None:
    shutdown_event = asyncio.Event()

    def _handle_signal() -> None:
        log.info("SIGTERM — shutting down inference")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    # Start Prometheus metrics HTTP server
    start_http_server(METRICS_PORT)
    log.info("Prometheus metrics", extra={"port": METRICS_PORT})

    redis = aioredis.from_url(REDIS_URL, decode_responses=False)
    pipeline = InferencePipeline()
    await pipeline.load_models()
    log.info("Inference service ready")

    try:
        while not shutdown_event.is_set():
            # Check queue length to avoid lag
            qlen = await redis.llen(FRAME_QUEUE)
            if qlen > 100:
                log.warning("Inference lagging, draining queue", extra={"qlen": qlen})
                # Keep the NEWEST one (at the tail), delete the rest
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
        from libs.shared.shm.ring_buffer import ReaderCache
        ReaderCache.clear()
        await redis.aclose()
        log.info("Inference service stopped")


if __name__ == "__main__":
    asyncio.run(run())
