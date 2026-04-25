"""Kafka publisher for tracking metadata snapshots."""

from __future__ import annotations

from typing import Any

from aiokafka import AIOKafkaProducer

from src.observability.metrics import NullMetricsRecorder, PrometheusMetrics
from src.schemas.tracking_events import (
    TrackingKafkaEventPayload,
    TrackingKafkaTrackPayload,
)
from src.services.tracking.contracts import TrackingTrackSnapshot


class KafkaTrackingUpdatePublisher:  # pylint: disable=too-few-public-methods
    """Publish tracking snapshots to Kafka for downstream consumers."""

    def __init__(
        self,
        producer: AIOKafkaProducer,
        topic: str,
        metrics_recorder: PrometheusMetrics | NullMetricsRecorder | None = None,
    ) -> None:
        self._producer = producer
        self._topic = topic
        self._metrics_recorder = metrics_recorder or NullMetricsRecorder()

    async def publish(
        self,
        *,
        camera_id: str,
        stream_name: str,
        annotated_stream_name: str,
        tracks: list[TrackingTrackSnapshot],
        frame: Any = None,
    ) -> None:
        del frame

        payload = TrackingKafkaEventPayload(
            camera_id=camera_id,
            stream_name=stream_name,
            annotated_stream_name=annotated_stream_name,
            active_tracks=len(tracks),
            tracks=[
                TrackingKafkaTrackPayload(
                    track_id=track.track_id,
                    persistent_id=track.persistent_id,
                    class_name=track.class_name,
                    confidence=track.confidence,
                    similarity=track.similarity,
                    left=track.left,
                    top=track.top,
                    width=track.width,
                    height=track.height,
                )
                for track in tracks
            ],
        )
        try:
            await self._producer.send_and_wait(
                self._topic,
                payload.model_dump(mode="json"),
                key=camera_id,
            )
        except Exception:
            self._metrics_recorder.increment_tracking_kafka_publish_failures()
            raise
        self._metrics_recorder.increment_tracking_kafka_messages_published()
