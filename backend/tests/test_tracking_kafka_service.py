from __future__ import annotations

from aiokafka.errors import KafkaConnectionError
from src.core.config import Settings
from src.services.realtime_video.contracts import TrackingTrackSnapshot
from src.services.tracking_kafka.publisher import KafkaTrackingUpdatePublisher
from src.services.tracking_kafka.service import TrackingKafkaProducerService


class FailingProducer:
    def __init__(self, *_args, **_kwargs) -> None:
        self.stop_called = False

    async def start(self) -> None:
        raise KafkaConnectionError("boom")

    async def stop(self) -> None:
        self.stop_called = True


class RecordingProducer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def send_and_wait(self, topic: str, value: object, *, key: str | None = None) -> None:
        self.calls.append(
            {
                "topic": topic,
                "value": value,
                "key": key,
            },
        )


async def test_tracking_kafka_producer_start_cleans_up_failed_producer(
    monkeypatch,
) -> None:
    created: list[FailingProducer] = []

    def build_producer(*args, **kwargs) -> FailingProducer:
        producer = FailingProducer(*args, **kwargs)
        created.append(producer)
        return producer

    monkeypatch.setattr(
        "src.services.tracking_kafka.service.AIOKafkaProducer",
        build_producer,
    )
    settings = Settings(
        database_url="postgresql://postgres:postgres@localhost:5432/test_db",
        kafka_enabled=True,
        _env_file=None,
    )
    service = TrackingKafkaProducerService(settings)

    await service.start()

    assert len(created) == 1
    assert created[0].stop_called is True
    assert service.health_snapshot()["healthy"] is False
    assert service.health_snapshot()["last_error"] == "KafkaConnectionError: boom"


async def test_tracking_kafka_publisher_sends_camera_scoped_payload() -> None:
    producer = RecordingProducer()
    publisher = KafkaTrackingUpdatePublisher(producer, "camera.tracking.updates")

    await publisher.publish(
        camera_id="cam_123",
        stream_name="front_gate",
        annotated_stream_name="front_gate_tracked",
        tracks=[
            TrackingTrackSnapshot(
                track_id="7",
                persistent_id="person_abc",
                class_name="person",
                confidence=0.94,
                similarity=0.88,
                left=10,
                top=20,
                width=30,
                height=40,
            ),
        ],
    )

    assert producer.calls == [
        {
            "topic": "camera.tracking.updates",
            "key": "cam_123",
            "value": {
                "event": "tracking.updated",
                "camera_id": "cam_123",
                "stream_name": "front_gate",
                "annotated_stream_name": "front_gate_tracked",
                "active_tracks": 1,
                "tracks": [
                    {
                        "track_id": "7",
                        "persistent_id": "person_abc",
                        "class_name": "person",
                        "confidence": 0.94,
                        "similarity": 0.88,
                        "left": 10,
                        "top": 20,
                        "width": 30,
                        "height": 40,
                    },
                ],
                "emitted_at": producer.calls[0]["value"]["emitted_at"],
            },
        },
    ]
