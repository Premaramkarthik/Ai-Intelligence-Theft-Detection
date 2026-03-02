"""
Alerting service main — Redis consumer for predictions.
Entry: python -m services.alerting.main
"""
from __future__ import annotations

import asyncio
import json
import os
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
    pubsub = redis.pubsub()
    await pubsub.subscribe("predictions")

    telegram = TelegramService()
    mqtt = MQTTService()

    log.info("Alerting service ready")
    try:
        while not shutdown_event.is_set():
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg:
                data = json.loads(msg["data"])
                # Alerting logic
                if data.get("confidence", 0) > cfg.alert_confidence_threshold:
                    await telegram.send_alert(f"Alert: {data['label']} detected!")
                    await mqtt.publish("alerts", data)
                    alerts_sent.inc()
            await asyncio.sleep(0.1)
    finally:
        await pubsub.unsubscribe("predictions")
        await redis.aclose()
        log.info("Alerting service stopped")


if __name__ == "__main__":
    asyncio.run(run())
