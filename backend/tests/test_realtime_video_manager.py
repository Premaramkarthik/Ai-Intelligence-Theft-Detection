"""Tests for the MediaMTX-backed stream manager."""

from __future__ import annotations

import asyncio

from src.services.realtime_video.queue import FrameQueue
from src.services.realtime_video.stream_manager import MediaMtxStreamManager


class FakeWorker:
    """Minimal worker double used to test manager orchestration."""

    def __init__(
        self,
        config,
        frame_queue,
        event_publisher,
        metrics_recorder,
        connection_alert_publisher,
    ) -> None:
        """Capture the worker dependencies created by the manager."""

        self.config = config
        self.frame_queue = frame_queue
        self.event_publisher = event_publisher
        self.metrics_recorder = metrics_recorder
        self.connection_alert_publisher = connection_alert_publisher
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        """Remain idle until cancellation."""

        await self._stop_event.wait()

    async def stop(self) -> None:
        """Mark the worker as stopped."""

        self._stop_event.set()


async def test_stream_manager_builds_mediamtx_endpoints() -> None:
    """Expose predictable RTSP, HLS and WHEP endpoints for each stream."""

    manager = MediaMtxStreamManager(
        FrameQueue(),
        rtsp_base_url="rtsp://mediamtx:8554",
        hls_base_url="http://mediamtx:8888",
        whep_base_url="http://mediamtx:8889",
    )

    endpoints = manager.stream_endpoints("front_gate")

    assert endpoints.rtsp_pull_url == "rtsp://mediamtx:8554/front_gate"
    assert endpoints.hls_url == "http://mediamtx:8888/front_gate/index.m3u8"
    assert endpoints.whep_url == "http://mediamtx:8889/front_gate/whep"


async def test_stream_manager_runs_multiple_workers_in_one_loop() -> None:
    """Create and stop multiple camera workers from the same manager instance."""

    manager = MediaMtxStreamManager(
        FrameQueue(),
        worker_factory=FakeWorker,
    )

    await manager.start_stream("cam_1", "front_gate", sample_fps=5.0)
    await manager.start_stream("cam_2", "warehouse", sample_fps=5.0)

    assert manager.active_cameras() == ["cam_1", "cam_2"]

    await manager.stop_all()

    assert manager.active_cameras() == []
