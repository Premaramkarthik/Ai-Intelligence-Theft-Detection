"""
Persistence service main — Redis consumer for DB writes.
Entry: python -m services.persistence.main
"""
from __future__ import annotations

import asyncio
import json
import os
import signal

import redis.asyncio as aioredis
from prometheus_client import start_http_server

from libs.shared.logging.logger import get_logger
from services.persistence.services.writer import DBWriter
from services.persistence.utils.metrics import METRICS_PORT

from libs.shared.core.settings import get_settings

log = get_logger(__name__)

cfg = get_settings()
REDIS_URL = cfg.redis_url


async def run() -> None:
    shutdown_event = asyncio.Event()

    def _handle_signal() -> None:
        log.info("SIGTERM — shutting down persistence")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    start_http_server(METRICS_PORT)
    log.info("Prometheus metrics", extra={"port": METRICS_PORT})

    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe("predictions")

    writer = DBWriter()
    await writer.connect()
    await writer.initialize_db()

    log.info("Persistence service ready")
    try:
        while not shutdown_event.is_set():
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg:
                data = json.loads(msg["data"])
                await writer.save_event(data)
            await asyncio.sleep(0.1)
    finally:
        await writer.disconnect()
        await pubsub.unsubscribe("predictions")
        await redis.aclose()
        log.info("Persistence service stopped")


if __name__ == "__main__":
    asyncio.run(run())
