from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from src.opencv_pipeline.buffering.frame_buffer import FrameBuffer
from src.opencv_pipeline.contracts import DropPolicy, FramePacket


def _packet(sequence_number: int, camera_id: str = "cam_1") -> FramePacket:
    return FramePacket(
        camera_id=camera_id,
        stream_name="front_gate",
        sequence_number=sequence_number,
        captured_at=datetime.now(timezone.utc),
        monotonic_ns=sequence_number,
        frame_bgr=np.zeros((8, 8, 3), dtype=np.uint8),
        width=8,
        height=8,
    )


async def test_frame_buffer_drop_oldest_keeps_latest_frame() -> None:
    buffer = FrameBuffer(maxsize=1, drop_policy=DropPolicy.drop_oldest)

    assert buffer.publish(_packet(1)) is True
    assert buffer.publish(_packet(2)) is True

    latest = await buffer.get()
    assert latest.sequence_number == 2


async def test_frame_buffer_drop_newest_rejects_overflow_frame() -> None:
    buffer = FrameBuffer(maxsize=1, drop_policy=DropPolicy.drop_newest)

    assert buffer.publish(_packet(1)) is True
    assert buffer.publish(_packet(2)) is False

    retained = await buffer.get()
    assert retained.sequence_number == 1


async def test_frame_buffer_discard_camera_removes_only_that_camera() -> None:
    buffer = FrameBuffer(maxsize=4, drop_policy=DropPolicy.drop_oldest)

    assert buffer.publish(_packet(1, camera_id="cam_1")) is True
    assert buffer.publish(_packet(2, camera_id="cam_2")) is True
    assert buffer.publish(_packet(3, camera_id="cam_1")) is True

    assert buffer.discard_camera("cam_1") == 2
    retained = await buffer.get()

    assert retained.camera_id == "cam_2"
    assert retained.sequence_number == 2
    assert buffer.empty() is True
