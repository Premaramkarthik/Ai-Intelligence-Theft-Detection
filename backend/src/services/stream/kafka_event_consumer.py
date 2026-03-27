from __future__ import annotations

import asyncio
import json

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from src.core.config import Settings
from src.core.logger.logger import get_logger
from src.schemas.stream_responses import StreamEventPayload
from src.services.presentation.websocket_manager import WebSocketManager
from src.services.stream.stream_service import StreamService


class StreamEventConsumer:
    def __init__(
        self,
        settings: Settings,
        stream_service: StreamService,
        websocket_manager: WebSocketManager,
    ) -> None:
        self._settings = settings
        self._stream_service = stream_service
        self._websocket_manager = websocket_manager
        self._logger = get_logger(__name__)
        self._consumer: AIOKafkaConsumer | None = None
        self._consumer_task: asyncio.Task[None] | None = None
        self._healthy = not settings.kafka_enabled
        self._last_error: str | None = None

    async def start(self) -> None:
        if not self._settings.kafka_enabled:
            return
        consumer = AIOKafkaConsumer(
            self._settings.kafka_topic_camera_status,
            self._settings.kafka_topic_camera_events,
            self._settings.kafka_topic_camera_ai_results,
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            group_id=self._settings.kafka_group_id,
            client_id=self._settings.kafka_client_id,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        )
        self._consumer = consumer
        try:
            await consumer.start()
        except (KafkaError, OSError, ConnectionError) as exc:
            self._healthy = False
            self._last_error = str(exc)
            self._logger.warning("Kafka consumer could not start: %s", exc)
            await self._safe_stop_consumer(consumer)
            self._consumer = None
            return
        self._healthy = True
        self._last_error = None
        self._consumer_task = asyncio.create_task(self._consume_loop())

    async def stop(self) -> None:
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            self._consumer_task = None
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None

    def health_snapshot(self) -> dict[str, str | bool | None]:
        return {
            "healthy": self._healthy,
            "last_error": self._last_error,
        }

    async def _consume_loop(self) -> None:
        if self._consumer is None:
            return
        async for message in self._consumer:
            try:
                event = StreamEventPayload.model_validate(message.value)
                websocket_event = await self._stream_service.build_websocket_event(event)
                await self._websocket_manager.broadcast(websocket_event)
            except Exception as exc:  # pylint: disable=broad-except
                self._healthy = False
                self._last_error = str(exc)
                self._logger.exception("Failed to process Kafka event: %s", exc)

    async def _safe_stop_consumer(self, consumer: AIOKafkaConsumer) -> None:
        try:
            await consumer.stop()
        except (KafkaError, OSError, ConnectionError) as exc:
            self._logger.debug("Kafka consumer cleanup failed after startup error: %s", exc)
