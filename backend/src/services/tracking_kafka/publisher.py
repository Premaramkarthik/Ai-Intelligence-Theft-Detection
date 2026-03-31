from __future__ import annotations

from aiokafka import AIOKafkaProducer

from src.schemas.tracking_events import (
    TrackingKafkaEventPayload,
    TrackingKafkaTrackPayload,
)
from src.services.realtime_video.contracts import TrackingTrackSnapshot


class KafkaTrackingUpdatePublisher:
    """Publish tracking snapshots to Kafka for downstream consumers."""

    def __init__(self, producer: AIOKafkaProducer, topic: str) -> None:
        self._producer = producer
        self._topic = topic

    async def publish(
        self,
        *,
        camera_id: str,
        stream_name: str,
        annotated_stream_name: str,
        tracks: list[TrackingTrackSnapshot],
    ) -> None:
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
        await self._producer.send_and_wait(
            self._topic,
            payload.model_dump(mode="json"),
            key=camera_id,
        )
