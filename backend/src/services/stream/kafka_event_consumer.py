"""Kafka consumer that rebroadcasts pipeline events to websocket clients."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from src.core.config import Settings
from src.core.logger.logger import get_logger
from src.observability.metrics import NullMetricsRecorder, PrometheusMetrics
from src.schemas.common import WebSocketEnvelope
from src.services.presentation.websocket_manager import WebSocketManager


def _deserialize_kafka_value(value: bytes | bytearray | memoryview | None) -> Any:
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytearray):
        value = bytes(value)
    return json.loads(value.decode("utf-8"))


def _format_exception(exc: BaseException) -> str:
    """Return a concise exception string without duplicated class prefixes."""

    message = str(exc)
    class_name = exc.__class__.__name__
    if message.startswith(f"{class_name}:"):
        return message
    return f"{class_name}: {message}"


class StreamEventConsumer:
    """Consume Kafka events and rebroadcast them through the websocket manager."""

    def __init__(
        self,
        settings: Settings,
        stream_service: object | None,
        websocket_manager: WebSocketManager,
        metrics_recorder: PrometheusMetrics | NullMetricsRecorder | None = None,
    ) -> None:
        self._settings = settings
        self._stream_service = stream_service
        self._websocket_manager = websocket_manager
        self._logger = get_logger(__name__)
        self._consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task[None] | None = None
        self._healthy = not settings.kafka_enabled
        self._last_error: str | None = None
        self._metrics_recorder = metrics_recorder or NullMetricsRecorder()

    async def start(self) -> None:
        """Start the Kafka consumer when Kafka integration is enabled."""

        if not self._settings.kafka_enabled:
            return

        consumer = AIOKafkaConsumer(
            self._settings.kafka_topic_camera_tracking_updates,
            self._settings.kafka_topic_camera_ai_results,
            self._settings.kafka_topic_camera_frames,
            self._settings.kafka_topic_identity_events,
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            group_id=f"{self._settings.kafka_group_id}-stream-events",
            client_id=f"{self._settings.kafka_client_id}-stream-events",
            value_deserializer=_deserialize_kafka_value,
        )
        try:
            await consumer.start()
        except (KafkaError, OSError, ConnectionError) as exc:
            self._healthy = False
            self._last_error = _format_exception(exc)
            self._logger.warning("Stream event consumer could not start: %s", exc)
            try:
                await consumer.stop()
            except (KafkaError, OSError, ConnectionError):
                pass
            return

        self._consumer = consumer
        self._healthy = True
        self._last_error = None
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the Kafka consumer and its background read loop."""

        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None

    def health_snapshot(self) -> dict[str, str | bool | None]:
        """Return the latest health state for use by health checks and metrics."""

        return {
            "healthy": self._healthy,
            "last_error": self._last_error,
        }

    async def _run_loop(self) -> None:
        assert self._consumer is not None
        try:
            async for message in self._consumer:
                try:
                    await self._handle_message(message.topic, message.value)
                    self._healthy = True
                    self._last_error = None
                    self._metrics_recorder.increment_stream_kafka_messages_consumed(
                        message.topic
                    )
                except Exception as exc:  # pylint: disable=broad-except
                    self._healthy = False
                    self._last_error = _format_exception(exc)
                    self._metrics_recorder.increment_stream_kafka_consumer_failures()
                    self._logger.warning(
                        "Stream event consumer failed to handle topic %s: %s",
                        message.topic,
                        exc,
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            self._healthy = False
            self._last_error = _format_exception(exc)
            self._metrics_recorder.increment_stream_kafka_consumer_failures()
            self._logger.warning("Stream event consumer loop failed: %s", exc)

    async def _handle_message(self, topic: str, payload: Any) -> None:
        data = payload if isinstance(payload, dict) else {"value": payload}
        event_type = str(data.get("event") or _default_event_type(topic))
        camera_id = data.get("camera_id")
        await self._websocket_manager.broadcast(
            WebSocketEnvelope(
                type=event_type,
                topic=topic,
                message=f"{event_type} received from Kafka.",
                camera_id=str(camera_id) if camera_id is not None else None,
                data=data,
            )
        )


def _default_event_type(topic: str) -> str:
    if topic.endswith("tracking.updates"):
        return "tracking.updated"
    if topic.endswith("ai_results"):
        return "inference.updated"
    if topic.endswith("frames"):
        return "camera.frame"
    if topic.endswith("identity.events"):
        return "identity.updated"
    return "stream.event"
