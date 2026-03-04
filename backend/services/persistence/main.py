"""
Persistence service main — consumes from Redis Stream for DB writes.
Entry: python -m services.persistence.main

Uses Redis Streams (XREADGROUP) instead of Pub/Sub for:
  - Guaranteed delivery (no lost writes)
  - Consumer groups
  - Message acknowledgment after successful DB write
  - Graceful shutdown with in-flight drain
"""
from __future__ import annotations

import asyncio
import json
import signal

import redis.asyncio as aioredis
from prometheus_client import start_http_server

from shared.logging.logger import get_logger
from services.persistence.services.writer import DBWriter
from services.persistence.utils.metrics import METRICS_PORT

from shared.core.settings import get_settings

log = get_logger(__name__)

cfg = get_settings()
REDIS_URL = cfg.redis_url
STREAM_KEY = "stream:predictions"
GROUP_NAME = "persistence_group"
CONSUMER_NAME = "persistence_worker_0"


async def _ensure_consumer_group(redis: aioredis.Redis) -> None:
    """Create the consumer group if it doesn't exist."""
    try:
        await redis.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        log.info("Created consumer group", extra={"group": GROUP_NAME, "stream": STREAM_KEY})
    except aioredis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            pass  # Group already exists
        else:
            raise


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
    await _ensure_consumer_group(redis)

    writer = DBWriter()
    await writer.connect()
    await writer.initialize_db()

    log.info("Persistence service ready (Redis Streams)")
    try:
        while not shutdown_event.is_set():
            entries = await redis.xreadgroup(
                GROUP_NAME, CONSUMER_NAME,
                {STREAM_KEY: ">"},
                count=20, block=1000,
            )
            if not entries:
                continue

            for _stream_name, messages in entries:
                for msg_id, fields in messages:
                    try:
                        data = json.loads(fields.get("payload", "{}"))
                        await writer.save_event(data)
                        await redis.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    except Exception as exc:
                        log.error("Write failed", extra={"msg_id": msg_id, "error": str(exc)})

        # Graceful drain — process remaining pending messages before exit
        log.info("Draining pending messages before shutdown...")
        pending = await redis.xreadgroup(
            GROUP_NAME, CONSUMER_NAME,
            {STREAM_KEY: "0"},
            count=100,
        )
        if pending:
            for _stream_name, messages in pending:
                for msg_id, fields in messages:
                    try:
                        data = json.loads(fields.get("payload", "{}"))
                        await writer.save_event(data)
                        await redis.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    except Exception:
                        pass
    finally:
        await writer.disconnect()
        await redis.aclose()
        log.info("Persistence service stopped")


if __name__ == "__main__":
    asyncio.run(run())
