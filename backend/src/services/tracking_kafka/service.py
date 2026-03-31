from __future__ import annotations

import json

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.core.config import Settings
from src.core.logger.logger import get_logger
from src.services.tracking.updates import NullTrackingUpdatePublisher, TrackingUpdatePublisher
from src.services.tracking_kafka.publisher import KafkaTrackingUpdatePublisher


def _serialize_kafka_key(value: str | None) -> bytes | None:
    if value is None:
        return None
    return value.encode("utf-8")


def _serialize_kafka_value(value: object) -> bytes:
    return json.dumps(value).encode("utf-8")


class TrackingKafkaProducerService:
    """Manage the Kafka producer used for tracking metadata events."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger(__name__)
        self._producer: AIOKafkaProducer | None = None
        self._healthy = not settings.kafka_enabled
        self._last_error: str | None = None

    async def start(self) -> None:
        if not self._settings.kafka_enabled:
            return

        producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            client_id=f"{self._settings.kafka_client_id}-tracking",
            acks="all",
            enable_idempotence=True,
            key_serializer=_serialize_kafka_key,
            value_serializer=_serialize_kafka_value,
        )
        try:
            await producer.start()
        except (KafkaError, OSError, ConnectionError) as exc:
            self._healthy = False
            self._last_error = str(exc)
            self._logger.warning("Tracking Kafka producer could not start: %s", exc)
            await self._safe_stop_producer(producer)
            return

        self._producer = producer
        self._healthy = True
        self._last_error = None

    async def stop(self) -> None:
        if self._producer is None:
            return
        await self._producer.stop()
        self._producer = None

    def publisher(self) -> TrackingUpdatePublisher:
        if self._producer is None:
            return NullTrackingUpdatePublisher()
        return KafkaTrackingUpdatePublisher(
            self._producer,
            self._settings.kafka_topic_camera_tracking_updates,
        )

    def health_snapshot(self) -> dict[str, str | bool | None]:
        return {
            "healthy": self._healthy,
            "last_error": self._last_error,
        }

    async def _safe_stop_producer(self, producer: AIOKafkaProducer) -> None:
        try:
            await producer.stop()
        except (KafkaError, OSError, ConnectionError) as exc:
            self._logger.debug(
                "Tracking Kafka producer cleanup failed after startup error: %s",
                exc,
            )
