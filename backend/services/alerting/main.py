"""
Alerting service main - consumes canonical incident events from Redis Streams.
"""
from __future__ import annotations

import asyncio
import json
import signal

import redis.asyncio as aioredis

from services.alerting.services.mqtt import MQTTService
from services.alerting.services.telegram import TelegramService
from services.alerting.utils.metrics import (
    METRICS_PORT,
    alerting_ready,
    alerts_failed,
    alerts_sent,
    redis_reconnects,
)
from shared.core.settings import get_settings
from shared.logging.logger import get_logger
from shared.redis.keys import INCIDENT_STREAM_KEY
from shared.runtime import RuntimeState, next_backoff_delay, start_runtime_server
from shared.types.events import IncidentEvent

log = get_logger(__name__)

cfg = get_settings()
REDIS_URL = cfg.redis_url
STREAM_KEY = INCIDENT_STREAM_KEY
GROUP_NAME = "alerting_group"
CONSUMER_NAME = "alerting_worker_0"


async def _ensure_consumer_group(redis: aioredis.Redis) -> None:
    try:
        await redis.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        log.info("Created consumer group", extra={"group": GROUP_NAME, "stream": STREAM_KEY})
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def run() -> None:
    shutdown_event = asyncio.Event()
    state = RuntimeState(service_name="alerting")
    runner, _site = await start_runtime_server(state, host=cfg.metrics_bind_host, port=METRICS_PORT)
    state.set_booted(True)

    def _handle_signal() -> None:
        log.info("SIGTERM - shutting down alerting")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            signal.signal(sig, lambda _signum, _frame: _handle_signal())

    telegram = TelegramService()
    mqtt = MQTTService()
    redis: aioredis.Redis | None = None
    attempt = 0

    try:
        while not shutdown_event.is_set():
            try:
                if redis is None:
                    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
                    await redis.ping()
                    await _ensure_consumer_group(redis)
                    state.dependency("redis", True, "connected")
                    state.dependency("telegram", bool(cfg.telegram_bot_token), "configured" if cfg.telegram_bot_token else "disabled")
                    state.dependency("mqtt", True, "configured")
                    state.update_detail(stream=STREAM_KEY, consumer_group=GROUP_NAME)
                    state.set_ready(True)
                    alerting_ready.set(1)
                    attempt = 0

                entries = await redis.xreadgroup(
                    GROUP_NAME,
                    CONSUMER_NAME,
                    {STREAM_KEY: ">"},
                    count=10,
                    block=1000,
                )
                if not entries:
                    continue

                for _stream_name, messages in entries:
                    for msg_id, fields in messages:
                        event: IncidentEvent | None = None
                        try:
                            event = IncidentEvent.model_validate(json.loads(fields.get("payload", "{}")))
                            if event.confidence >= cfg.alert_confidence_threshold:
                                await telegram.send_shoplifting_alert(
                                    camera_id=event.camera_id,
                                    confidence=event.confidence,
                                    timestamp=event.timestamp,
                                )
                                await mqtt.publish("alerts", event.model_dump(mode="json"))
                                alerts_sent.inc()
                            await redis.xack(STREAM_KEY, GROUP_NAME, msg_id)
                        except Exception as exc:
                            alerts_failed.inc()
                            log.error(
                                "Alert processing failed",
                                extra={"msg_id": msg_id, "error": str(exc), "trace_id": event.trace_id if event else None},
                            )
            except Exception as exc:
                delay = next_backoff_delay(attempt)
                redis_reconnects.inc()
                alerting_ready.set(0)
                state.set_degraded(True)
                state.dependency("redis", False, str(exc))
                log.warning("Alerting degraded; retrying", extra={"error": str(exc), "delay": delay})
                if redis is not None:
                    await redis.aclose()
                    redis = None
                await asyncio.sleep(delay)
                attempt += 1
    finally:
        if redis is not None:
            await redis.aclose()
        await runner.cleanup()
        log.info("Alerting service stopped")


if __name__ == "__main__":
    asyncio.run(run())
