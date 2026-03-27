"""Optional Kafka publisher for frame metadata events."""

from __future__ import annotations

import json
from typing import Protocol

from src.core.logger.logger import get_logger
from src.services.realtime_video.contracts import FrameSample


class FrameEventPublisher(Protocol):
    """Protocol implemented by frame event publishers."""

    async def publish(self, frame: FrameSample) -> None:
        """Publish frame metadata for downstream event consumers."""


class NullFrameEventPublisher:
    """No-op publisher used when Kafka is disabled or not required."""

    async def publish(self, frame: FrameSample) -> None:
        """Discard the frame metadata event."""

        del frame


class KafkaFrameEventPublisher:
    """Publish frame metadata to Kafka without transporting image payloads."""

    def __init__(self, producer: object, topic: str) -> None:
        """Create a publisher backed by an external aiokafka producer."""

        self._producer = producer
        self._topic = topic
        self._logger = get_logger(__name__)

    async def publish(self, frame: FrameSample) -> None:
        """Publish a JSON event containing only frame metadata."""

        payload = {
            "camera_id": frame.camera_id,
            "stream_name": frame.stream_name,
            "sequence_number": frame.sequence_number,
            "sampled_at": frame.sampled_at.isoformat(),
            "source_timestamp_seconds": frame.source_timestamp_seconds,
            "width": frame.width,
            "height": frame.height,
            "pixel_format": frame.pixel_format,
        }
        send_and_wait = getattr(self._producer, "send_and_wait", None)
        if send_and_wait is None:
            self._logger.warning("Kafka producer does not expose send_and_wait().")
            return
        await send_and_wait(self._topic, json.dumps(payload).encode("utf-8"))
