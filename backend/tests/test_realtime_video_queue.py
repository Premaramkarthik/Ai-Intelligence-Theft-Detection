"""Tests for the in-memory frame queue."""

from __future__ import annotations

from src.services.realtime_video.contracts import FrameSample
from src.services.realtime_video.queue import FrameQueue, QueueDropPolicy


async def test_frame_queue_drops_oldest_when_full() -> None:
    """Drop the oldest frame when the queue is full and configured to do so."""

    queue = FrameQueue(maxsize=1, drop_policy=QueueDropPolicy.drop_oldest)
    await queue.publish(FrameSample(camera_id="cam_1", stream_name="cam_1", sequence_number=1))
    await queue.publish(FrameSample(camera_id="cam_1", stream_name="cam_1", sequence_number=2))

    frame = await queue.consume()

    assert frame.sequence_number == 2
    assert queue.metrics().dropped_frames == 1


async def test_frame_queue_drops_newest_when_full() -> None:
    """Drop the incoming frame when the queue is full and configured to do so."""

    queue = FrameQueue(maxsize=1, drop_policy=QueueDropPolicy.drop_newest)
    await queue.publish(FrameSample(camera_id="cam_1", stream_name="cam_1", sequence_number=1))
    accepted = await queue.publish(
        FrameSample(camera_id="cam_1", stream_name="cam_1", sequence_number=2),
    )

    frame = await queue.consume()

    assert accepted is False
    assert frame.sequence_number == 1
    assert queue.metrics().dropped_frames == 1
