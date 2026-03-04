"""
Alerting service main — consumes from Redis Stream with consumer groups.
Entry: python -m services.alerting.main

Uses Redis Streams (XREADGROUP) instead of Pub/Sub for:
  - Message persistence (survives restart)
  - Consumer groups (load-balanced if scaled)
  - Message acknowledgment (no lost alerts)
"""
from __future__ import annotations

import asyncio
import json
import signal

import redis.asyncio as aioredis
from prometheus_client import start_http_server

from shared.logging.logger import get_logger
from shared.core.settings import get_settings
from services.alerting.utils.metrics import METRICS_PORT, alerts_sent
from services.alerting.services.telegram import TelegramService
from services.alerting.services.mqtt import MQTTService

log = get_logger(__name__)

cfg = get_settings()
REDIS_URL = cfg.redis_url
STREAM_KEY = "stream:predictions"
GROUP_NAME = "alerting_group"
CONSUMER_NAME = "alerting_worker_0"


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
        log.info("SIGTERM — shutting down alerting")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    start_http_server(METRICS_PORT)
    log.info("Prometheus metrics", extra={"port": METRICS_PORT})

    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    await _ensure_consumer_group(redis)

    telegram = TelegramService()
    mqtt = MQTTService()

    log.info("Alerting service ready (Redis Streams)")
    try:
        while not shutdown_event.is_set():
            # Read from stream with consumer group — blocks up to 1s
            entries = await redis.xreadgroup(
                GROUP_NAME, CONSUMER_NAME,
                {STREAM_KEY: ">"},
                count=10, block=1000,
            )
            if not entries:
                continue

            for _stream_name, messages in entries:
                for msg_id, fields in messages:
                    try:
                        data = json.loads(fields.get("payload", "{}"))
                        action = data.get("action", {})
                        label = action.get("label", "")
                        confidence = action.get("confidence", 0)
                        camera_id = data.get("camera_id", "unknown")

                        if label == "shoplifting" and confidence > cfg.alert_confidence_threshold:
                            await telegram.send_shoplifting_alert(
                                camera_id=camera_id,
                                confidence=confidence,
                                timestamp=data.get("ts"),
                            )
                            await mqtt.publish("alerts", data)
                            alerts_sent.inc()
                        # Acknowledge message
                        await redis.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    except Exception as exc:
                        log.error("Alert processing failed", extra={"msg_id": msg_id, "error": str(exc)})
    finally:
        await redis.aclose()
        log.info("Alerting service stopped")


if __name__ == "__main__":
    asyncio.run(run())
