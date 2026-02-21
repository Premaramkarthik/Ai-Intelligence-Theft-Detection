"""MQTT alert publisher."""
from __future__ import annotations

import json
from libs.shared.logging.logger import get_logger
from libs.shared.core.settings import get_settings

log = get_logger(__name__)

class MQTTService:
    def __init__(self) -> None:
        self._cfg = get_settings()

    async def publish(self, topic: str, payload: dict) -> None:
        """Mock MQTT publish — real implementation would use gmqtt or paho."""
        log.info("MQTT Publish", extra={"topic": topic, "payload": payload})
