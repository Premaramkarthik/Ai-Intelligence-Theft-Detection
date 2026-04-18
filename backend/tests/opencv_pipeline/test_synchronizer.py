from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from src.opencv_pipeline.buffering.synchronizer import MultiCameraSynchronizer
from src.opencv_pipeline.contracts import FramePacket


def _packet(camera_id: str, monotonic_ns: int, sequence_number: int) -> FramePacket:
    return FramePacket(
        camera_id=camera_id,
        stream_name=camera_id,
        sequence_number=sequence_number,
        captured_at=datetime.now(timezone.utc),
        monotonic_ns=monotonic_ns,
        frame_bgr=np.zeros((8, 8, 3), dtype=np.uint8),
        width=8,
        height=8,
    )


def test_multi_camera_synchronizer_emits_bundle_within_tolerance() -> None:
    synchronizer = MultiCameraSynchronizer(["cam_1", "cam_2"], tolerance_ms=15.0)

    assert synchronizer.submit(_packet("cam_1", 1_000_000_000, 1)) is None
    bundle = synchronizer.submit(_packet("cam_2", 1_010_000_000, 1))

    assert bundle is not None
    assert bundle.span_ms == 10.0
    assert [packet.camera_id for packet in bundle.packets] == ["cam_1", "cam_2"]


def test_multi_camera_synchronizer_waits_when_frames_are_too_far_apart() -> None:
    synchronizer = MultiCameraSynchronizer(["cam_1", "cam_2"], tolerance_ms=5.0)

    assert synchronizer.submit(_packet("cam_1", 1_000_000_000, 1)) is None
    assert synchronizer.submit(_packet("cam_2", 1_020_000_000, 1)) is None


def test_multi_camera_synchronizer_discards_removed_camera_state() -> None:
    synchronizer = MultiCameraSynchronizer(["cam_1", "cam_2"], tolerance_ms=15.0)
    assert synchronizer.submit(_packet("cam_1", 1_000_000_000, 1)) is None

    synchronizer.remove_camera("cam_1")
    bundle = synchronizer.submit(_packet("cam_2", 1_001_000_000, 1))

    assert bundle is not None
    assert [packet.camera_id for packet in bundle.packets] == ["cam_2"]
