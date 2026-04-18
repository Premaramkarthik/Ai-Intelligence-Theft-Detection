"""Timestamp-based multi-camera frame synchronization."""

from __future__ import annotations

from dataclasses import dataclass

from src.opencv_pipeline.contracts import FramePacket, SynchronizedFrameBundle, utc_now


@dataclass(slots=True)
class _CameraClockState:
    packet: FramePacket
    emitted_sequence: int = -1


class MultiCameraSynchronizer:
    """Synchronize the latest frame from each camera within a time window."""

    def __init__(self, camera_ids: list[str], tolerance_ms: float) -> None:
        self._camera_ids = tuple(camera_ids)
        self._tolerance_ms = max(tolerance_ms, 0.0)
        self._latest: dict[str, _CameraClockState] = {}
        self._bundle_id = 0

    def submit(self, packet: FramePacket) -> SynchronizedFrameBundle | None:
        """Submit one frame and return a bundle if all cameras are aligned."""

        self._latest[packet.camera_id] = _CameraClockState(packet=packet)
        if any(camera_id not in self._latest for camera_id in self._camera_ids):
            return None

        packets = [self._latest[camera_id].packet for camera_id in self._camera_ids]
        newest = max(frame.monotonic_ns for frame in packets)
        oldest = min(frame.monotonic_ns for frame in packets)
        span_ms = (newest - oldest) / 1_000_000.0
        if span_ms > self._tolerance_ms:
            return None

        if all(
            self._latest[camera_id].emitted_sequence
            == self._latest[camera_id].packet.sequence_number
            for camera_id in self._camera_ids
        ):
            return None

        bundle = SynchronizedFrameBundle(
            bundle_id=self._bundle_id,
            emitted_at=utc_now(),
            packets=[packet for packet in packets],
            span_ms=span_ms,
        )
        self._bundle_id += 1
        for camera_id in self._camera_ids:
            state = self._latest[camera_id]
            state.emitted_sequence = state.packet.sequence_number
        return bundle

    def remove_camera(self, camera_id: str) -> None:
        """Discard synchronization state for a camera that is no longer active."""

        self._latest.pop(camera_id, None)
        self._camera_ids = tuple(
            active_camera_id
            for active_camera_id in self._camera_ids
            if active_camera_id != camera_id
        )
