"""Tests for monotonic timing in the PyAV frame worker."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from src.services.realtime_video.contracts import FrameSample, StreamWorkerConfig
from src.services.realtime_video.frame_worker import FrameSamplingGate, PyAvFrameWorker
from src.services.realtime_video.queue import FrameQueue, QueueDropPolicy


def test_frame_sampling_gate_uses_monotonic_ns(monkeypatch) -> None:
    """Base frame sampling decisions on monotonic nanoseconds instead of wall time."""

    ticks = iter([0, 50_000_000, 250_000_000])
    monkeypatch.setattr(
        "src.services.realtime_video.frame_worker.monotonic_ns",
        lambda: next(ticks),
    )
    gate = FrameSamplingGate(sample_fps=5.0)

    assert gate.should_emit() is True
    assert gate.should_emit() is False
    assert gate.should_emit() is True


def test_frame_sampling_gate_clamps_non_positive_fps() -> None:
    """Clamp non-positive FPS values to a safe minimum instead of emitting everything."""

    gate = FrameSamplingGate(sample_fps=0.0)

    assert gate._sample_interval_ns == 10_000_000_000  # pylint: disable=protected-access


async def test_worker_publish_sample_to_loop_records_queue_metrics() -> None:
    """Record queue and worker metrics when a sampled frame is queued from the decode thread."""

    worker = PyAvFrameWorker(
        StreamWorkerConfig(
            camera_id="cam_1",
            stream_name="cam_1",
            mediamtx_rtsp_url="rtsp://192.168.1.2:8080/h264_ulaw.sdp",
        ),
        FrameQueue(maxsize=2),
        AsyncMock(),
    )
    sample = FrameSample(
        camera_id="cam_1",
        stream_name="cam_1",
        sequence_number=1,
    )

    worker._publish_sample_to_loop(sample)  # pylint: disable=protected-access
    await asyncio.sleep(0)

    metrics = worker.metrics()

    assert metrics.last_frame_monotonic_ns == sample.sampled_monotonic_ns
    assert metrics.queue_latency_ms >= 0.0


async def test_worker_publish_sample_to_loop_tracks_drops() -> None:
    """Track dropped frames when the bounded frame queue cannot accept more samples."""

    queue = FrameQueue(maxsize=1, drop_policy=QueueDropPolicy.drop_newest)
    await queue.publish(
        FrameSample(camera_id="cam_1", stream_name="cam_1", sequence_number=1),
    )
    worker = PyAvFrameWorker(
        StreamWorkerConfig(
            camera_id="cam_1",
            stream_name="cam_1",
            mediamtx_rtsp_url="rtsp://192.168.1.2:8080/h264_ulaw.sdp",
        ),
        queue,
        AsyncMock(),
    )
    sample = FrameSample(
        camera_id="cam_1",
        stream_name="cam_1",
        sequence_number=2,
    )

    worker._publish_sample_to_loop(sample)  # pylint: disable=protected-access

    assert worker.metrics().dropped_frames == 1


async def test_worker_emits_connection_alert_once_per_decode_session() -> None:
    """Emit a single connection alert after the first successfully queued frame."""

    alert_publisher = AsyncMock()
    worker = PyAvFrameWorker(
        StreamWorkerConfig(
            camera_id="cam_1",
            stream_name="cam_1",
            mediamtx_rtsp_url="rtsp://192.168.1.2:8080/h264_ulaw.sdp",
        ),
        FrameQueue(maxsize=4),
        AsyncMock(),
        connection_alert_publisher=alert_publisher,
    )

    worker._publish_sample_to_loop(  # pylint: disable=protected-access
        FrameSample(camera_id="cam_1", stream_name="cam_1", sequence_number=1),
    )
    worker._publish_sample_to_loop(  # pylint: disable=protected-access
        FrameSample(camera_id="cam_1", stream_name="cam_1", sequence_number=2),
    )
    await asyncio.sleep(0)

    alert_publisher.publish_camera_connected.assert_awaited_once_with("cam_1")
