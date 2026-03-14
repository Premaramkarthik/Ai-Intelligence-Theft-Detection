"""
Alerting service main - consumes canonical incident events from Redis Streams.
"""
from __future__ import annotations

import asyncio
import json
import signal

import redis.asyncio as aioredis
from prometheus_client import start_http_server

from services.alerting.services.mqtt import MQTTService
from services.alerting.services.telegram import TelegramService
from services.alerting.utils.metrics import METRICS_PORT, alerts_sent
from shared.core.settings import get_settings
from shared.logging.logger import get_logger
from shared.types.events import IncidentEvent

log = get_logger(__name__)

cfg = get_settings()
REDIS_URL = cfg.redis_url
STREAM_KEY = "stream:incidents"
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

    def _handle_signal() -> None:
        log.info("SIGTERM - shutting down alerting")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            signal.signal(sig, lambda _signum, _frame: _handle_signal())

    start_http_server(METRICS_PORT)
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    await redis.ping()
    await _ensure_consumer_group(redis)

    telegram = TelegramService()
    mqtt = MQTTService()

    try:
        while not shutdown_event.is_set():
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
                        log.error("Alert processing failed", extra={"msg_id": msg_id, "error": str(exc)})
    finally:
        await redis.aclose()
        log.info("Alerting service stopped")


if __name__ == "__main__":
    asyncio.run(run())
