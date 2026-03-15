"""
Persistence service main - consumes from Redis Stream for DB writes.
Entry: python -m services.persistence.main
"""
from __future__ import annotations

import asyncio
import json
import signal

import redis.asyncio as aioredis

from shared.core.settings import get_settings
from shared.logging.logger import get_logger
from shared.redis.keys import INCIDENT_STREAM_KEY
from shared.runtime import RuntimeState, next_backoff_delay, start_runtime_server
from services.persistence.services.writer import DBWriter
from services.persistence.utils.metrics import METRICS_PORT, persistence_ready, redis_reconnects

log = get_logger(__name__)

cfg = get_settings()
REDIS_URL = cfg.redis_url
STREAM_KEY = INCIDENT_STREAM_KEY
GROUP_NAME = "persistence_group"
CONSUMER_NAME = "persistence_worker_0"


async def _ensure_consumer_group(redis: aioredis.Redis) -> None:
    try:
        await redis.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        log.info("Created consumer group", extra={"group": GROUP_NAME, "stream": STREAM_KEY})
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def run() -> None:
    shutdown_event = asyncio.Event()
    state = RuntimeState(service_name="persistence")
    runner, _site = await start_runtime_server(state, host=cfg.metrics_bind_host, port=METRICS_PORT)
    state.set_booted(True)

    def _handle_signal() -> None:
        log.info("SIGTERM - shutting down persistence")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            signal.signal(sig, lambda _signum, _frame: _handle_signal())

    writer = DBWriter()
    redis: aioredis.Redis | None = None
    attempt = 0

    try:
        while not shutdown_event.is_set():
            try:
                if redis is None:
                    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
                    await redis.ping()
                    await _ensure_consumer_group(redis)
                    await writer.connect()
                    await writer.initialize_db()
                    await writer.ensure_connection()
                    state.dependency("redis", True, "connected")
                    state.dependency("postgres", True, "connected")
                    state.update_detail(stream=STREAM_KEY, consumer_group=GROUP_NAME)
                    state.set_ready(True)
                    persistence_ready.set(1)
                    attempt = 0
                    log.info("Persistence service ready (Redis Streams)")

                entries = await redis.xreadgroup(
                    GROUP_NAME,
                    CONSUMER_NAME,
                    {STREAM_KEY: ">"},
                    count=20,
                    block=1000,
                )
                if not entries:
                    continue

                for _stream_name, messages in entries:
                    for msg_id, fields in messages:
                        try:
                            data = json.loads(fields.get("payload", "{}"))
                            await writer.ensure_connection()
                            await writer.save_event(data)
                            await redis.xack(STREAM_KEY, GROUP_NAME, msg_id)
                        except Exception as exc:
                            log.error("Write failed", extra={"msg_id": msg_id, "error": str(exc)})
            except Exception as exc:
                delay = next_backoff_delay(attempt)
                redis_reconnects.inc()
                persistence_ready.set(0)
                state.set_degraded(True)
                state.dependency("redis", False, str(exc))
                state.dependency("postgres", False, str(exc))
                log.warning("Persistence degraded; retrying", extra={"error": str(exc), "delay": delay})
                if redis is not None:
                    await redis.aclose()
                    redis = None
                await writer.disconnect()
                await asyncio.sleep(delay)
                attempt += 1

        if redis is not None:
            log.info("Draining pending messages before shutdown...")
            pending = await redis.xreadgroup(
                GROUP_NAME,
                CONSUMER_NAME,
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
        if redis is not None:
            await redis.aclose()
        await runner.cleanup()
        log.info("Persistence service stopped")


if __name__ == "__main__":
    asyncio.run(run())
