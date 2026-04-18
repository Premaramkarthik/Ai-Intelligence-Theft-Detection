from __future__ import annotations

from src.services.tracking.contracts import TrackingTrackSnapshot
from src.services.tracking.updates import FanoutTrackingUpdatePublisher


class RecordingPublisher:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def publish(
        self,
        *,
        camera_id: str,
        stream_name: str,
        annotated_stream_name: str,
        tracks: list[TrackingTrackSnapshot],
        frame: object = None,
    ) -> None:
        self.calls.append(
            {
                "camera_id": camera_id,
                "stream_name": stream_name,
                "annotated_stream_name": annotated_stream_name,
                "tracks": tracks,
            },
        )


class FailingPublisher:
    async def publish(
        self,
        *,
        camera_id: str,
        stream_name: str,
        annotated_stream_name: str,
        tracks: list[TrackingTrackSnapshot],
        frame: object = None,
    ) -> None:
        del camera_id, stream_name, annotated_stream_name, tracks, frame
        raise RuntimeError("boom")


async def test_fanout_tracking_update_publisher_continues_after_failure() -> None:
    recording_publisher = RecordingPublisher()
    publisher = FanoutTrackingUpdatePublisher((FailingPublisher(), recording_publisher))

    tracks = [
        TrackingTrackSnapshot(
            track_id="1",
            persistent_id="person_1",
            class_name="person",
            confidence=0.91,
            similarity=0.87,
            left=1,
            top=2,
            width=3,
            height=4,
        ),
    ]

    await publisher.publish(
        camera_id="cam_1",
        stream_name="front_gate",
        annotated_stream_name="front_gate_tracked",
        tracks=tracks,
    )

    assert recording_publisher.calls == [
        {
            "camera_id": "cam_1",
            "stream_name": "front_gate",
            "annotated_stream_name": "front_gate_tracked",
            "tracks": tracks,
        },
    ]
