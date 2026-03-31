"""Tests for the annotated tracking stream manager."""

from __future__ import annotations

import asyncio

from src.services.tracking.manager import TrackingStreamManager


class FakeTrackingWorker:
    """Minimal tracking worker double used to test orchestration."""

    def __init__(
        self,
        config,
        detector,
        identity_store,
        update_publisher,
        embedder_weights_path,
    ) -> None:
        self.config = config
        self.detector = detector
        self.identity_store = identity_store
        self.update_publisher = update_publisher
        self.embedder_weights_path = embedder_weights_path
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        await self._stop_event.wait()

    async def stop(self) -> None:
        self._stop_event.set()

    def metrics(self):
        from src.services.realtime_video.contracts import TrackingWorkerMetrics

        return TrackingWorkerMetrics()


class FakeDetector:
    """Detector placeholder used by the manager tests."""


class FakeIdentityStore:
    """Identity store placeholder used by the manager tests."""

    def close(self) -> None:
        return None


async def test_tracking_manager_builds_annotated_endpoints() -> None:
    manager = TrackingStreamManager(
        detector=FakeDetector(),
        identity_store=FakeIdentityStore(),
        worker_factory=FakeTrackingWorker,
        ffmpeg_binary="ffmpeg",
        rtsp_base_url="rtsp://mediamtx:8554",
        hls_base_url="http://mediamtx:8888",
        whep_base_url="http://mediamtx:8889",
    )

    endpoints = manager.stream_endpoints("front_gate")

    assert endpoints.stream_name == "front_gate_tracked"
    assert endpoints.rtsp_pull_url == "rtsp://mediamtx:8554/front_gate_tracked"
    assert endpoints.hls_url == "http://mediamtx:8888/front_gate_tracked/index.m3u8"
    assert endpoints.whep_url == "http://mediamtx:8889/front_gate_tracked/whep"


async def test_tracking_manager_runs_multiple_workers_in_one_loop() -> None:
    manager = TrackingStreamManager(
        detector=FakeDetector(),
        identity_store=FakeIdentityStore(),
        worker_factory=FakeTrackingWorker,
        ffmpeg_binary="ffmpeg",
    )

    await manager.start_stream("cam_1", "front_gate")
    await manager.start_stream("cam_2", "warehouse")

    snapshot = manager.get_snapshot("cam_1", "front_gate")
    assert snapshot.enabled is True
    assert snapshot.is_registered is True
    assert snapshot.stream_name == "front_gate_tracked"

    await manager.stop_all()

    stopped_snapshot = manager.get_snapshot("cam_1", "front_gate")
    assert stopped_snapshot.enabled is False
    assert stopped_snapshot.is_process_alive is False
