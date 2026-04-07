"""Unit tests for the inference plane services."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from src.services.inference.batch_builder import BatchBuilder
from src.services.inference.contracts import (
    InferenceIngressSample,
    InferenceWorkerConfig,
)
from src.services.inference.decision_engine import DecisionEngine
from src.services.inference.ingress_scheduler import InferenceIngressScheduler
from src.services.inference.temporal_buffer import TemporalBufferService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_sample(
    camera_id: str = "cam_1",
    persistent_id: str = "person_1",
    persistent_id_state: str = "assigned",
    consecutive_hits: int = 10,
    frames_since_update: int = 0,
    width: int = 64,
    height: int = 128,
    sampled_at: datetime | None = None,
) -> InferenceIngressSample:
    return InferenceIngressSample(
        camera_id=camera_id,
        stream_name="stream_1",
        local_track_id="track_1",
        persistent_id=persistent_id,
        sampled_at=sampled_at or _utc_now(),
        left=10,
        top=10,
        width=width,
        height=height,
        crop=np.zeros((height, width, 3), dtype=np.uint8),
        age_frames=20,
        consecutive_hits=consecutive_hits,
        frames_since_update=frames_since_update,
        persistent_id_state=persistent_id_state,
    )


def _make_config(**overrides: object) -> InferenceWorkerConfig:
    defaults: dict[str, object] = {
        "camera_id": "cam_1",
        "strategy": "cnn_transformer",
        "temporal_buffer_size": 4,  # keep small for tests
        "dispatch_min_consecutive_hits": 4,
        "dispatch_min_crop_width": 32,
        "dispatch_min_crop_height": 64,
        "identity_gap_reset_seconds": 2.0,
        "ingress_queue_maxsize": 64,
        "score_warning_threshold": 0.5,
        "score_alert_threshold": 0.8,
    }
    defaults.update(overrides)
    return InferenceWorkerConfig(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TemporalBufferService
# ---------------------------------------------------------------------------


class TestTemporalBufferService:
    def test_push_and_depth(self) -> None:
        buf = TemporalBufferService(window_size=4)
        sample = _make_sample()
        buf.push(sample)
        assert buf.depth("person_1") == 1

    def test_rolling_window_evicts_oldest(self) -> None:
        buf = TemporalBufferService(window_size=4)
        for _ in range(6):
            buf.push(_make_sample())
        assert buf.depth("person_1") == 4

    def test_buffer_continues_across_camera_change(self) -> None:
        buf = TemporalBufferService(window_size=4)
        now = _utc_now()
        buf.push(_make_sample(camera_id="cam_1", sampled_at=now))
        buf.push(_make_sample(camera_id="cam_2", sampled_at=now + timedelta(milliseconds=100)))
        assert buf.depth("person_1") == 2

    def test_reset_on_two_second_gap(self) -> None:
        buf = TemporalBufferService(window_size=4, gap_reset_seconds=2.0)
        now = _utc_now()
        buf.push(_make_sample(sampled_at=now))
        buf.push(_make_sample(sampled_at=now + timedelta(seconds=3)))
        # second push triggered a reset, so depth is 1 (only the new frame)
        assert buf.depth("person_1") == 1

    def test_no_flush_on_strategy_switch(self) -> None:
        """Buffer is agnostic to strategy — no reset expected here."""
        buf = TemporalBufferService(window_size=4)
        for _ in range(3):
            buf.push(_make_sample())
        # Strategy switch does not touch the buffer
        assert buf.depth("person_1") == 3

    def test_reset_on_pending_state(self) -> None:
        buf = TemporalBufferService(window_size=4)
        now = _utc_now()
        buf.push(_make_sample(sampled_at=now))
        buf.push(_make_sample(persistent_id_state="pending", sampled_at=now + timedelta(milliseconds=50)))
        assert buf.depth("person_1") == 1


# ---------------------------------------------------------------------------
# InferenceIngressScheduler — dispatch gate
# ---------------------------------------------------------------------------


class TestInferenceIngressScheduler:
    def _make_scheduler(self, **config_overrides: object) -> InferenceIngressScheduler:
        cfg = _make_config(**config_overrides)
        buf = TemporalBufferService(
            window_size=cfg.temporal_buffer_size,
            gap_reset_seconds=cfg.identity_gap_reset_seconds,
        )
        return InferenceIngressScheduler(cfg, buf)

    def test_gate_passes_all_conditions_met(self) -> None:
        sched = self._make_scheduler(temporal_buffer_size=2)
        # Fill buffer to window_size
        sched.ingest(_make_sample())
        sched.ingest(_make_sample())
        assert sched.queue.qsize() == 1

    def test_gate_rejects_wrong_state(self) -> None:
        sched = self._make_scheduler(temporal_buffer_size=1)
        sched.ingest(_make_sample(persistent_id_state="pending"))
        assert sched.queue.qsize() == 0

    def test_gate_rejects_insufficient_consecutive_hits(self) -> None:
        sched = self._make_scheduler(
            temporal_buffer_size=1, dispatch_min_consecutive_hits=4
        )
        sched.ingest(_make_sample(consecutive_hits=3))
        assert sched.queue.qsize() == 0

    def test_gate_rejects_stale_frame(self) -> None:
        sched = self._make_scheduler(temporal_buffer_size=1)
        sched.ingest(_make_sample(frames_since_update=1))
        assert sched.queue.qsize() == 0

    def test_gate_rejects_small_crop(self) -> None:
        sched = self._make_scheduler(temporal_buffer_size=1)
        sched.ingest(_make_sample(width=10, height=10))
        assert sched.queue.qsize() == 0

    def test_gate_rejects_missing_buffer_depth(self) -> None:
        sched = self._make_scheduler(temporal_buffer_size=4)
        # Only one push — buffer depth 1 < 4
        sched.ingest(_make_sample())
        assert sched.queue.qsize() == 0


# ---------------------------------------------------------------------------
# BatchBuilder — tensor shapes
# ---------------------------------------------------------------------------


class TestBatchBuilder:
    def test_cnn_transformer_shape(self) -> None:
        builder = BatchBuilder()
        crops = [np.zeros((64, 32, 3), dtype=np.uint8) for _ in range(16)]
        tensors = builder.build(crops, "cnn_transformer")
        # BCTHW: (1, C, T, H, W) = (1, 3, 16, 224, 224)
        assert tensors["input"].shape == (1, 3, 16, 224, 224)

    def test_vjepa_probe_shape(self) -> None:
        builder = BatchBuilder()
        crops = [np.zeros((64, 32, 3), dtype=np.uint8) for _ in range(16)]
        tensors = builder.build(crops, "vjepa_probe")
        # BTCHW: (1, T, C, H, W) = (1, 16, 3, 224, 224)
        assert tensors["input"].shape == (1, 16, 3, 224, 224)

    def test_pixel_values_normalised(self) -> None:
        builder = BatchBuilder()
        white = [np.full((64, 32, 3), 255, dtype=np.uint8)]
        tensors = builder.build(white, "cnn_transformer")
        assert float(tensors["input"].max()) == pytest.approx(1.0, abs=1e-3)


# ---------------------------------------------------------------------------
# DecisionEngine — threshold → alert_level
# ---------------------------------------------------------------------------


class TestDecisionEngine:
    def _make_engine(
        self, warning: float = 0.5, alert: float = 0.8
    ) -> DecisionEngine:
        cfg = _make_config(score_warning_threshold=warning, score_alert_threshold=alert)
        return DecisionEngine(cfg)

    def test_below_warning_is_normal(self) -> None:
        assert self._make_engine().classify(0.3) == "normal"

    def test_at_warning_threshold(self) -> None:
        assert self._make_engine().classify(0.5) == "warning"

    def test_at_alert_threshold(self) -> None:
        assert self._make_engine().classify(0.8) == "alert"

    def test_above_alert_threshold(self) -> None:
        assert self._make_engine().classify(0.95) == "alert"

    def test_between_thresholds_is_warning(self) -> None:
        assert self._make_engine().classify(0.65) == "warning"


# ---------------------------------------------------------------------------
# InferenceEventRepository — save skips normal, persists non-normal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_repository_skips_normal_alert_level() -> None:
    from src.services.inference.event_repository import InferenceEventRepository

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    repo = InferenceEventRepository(mock_pool)
    await repo.save(
        camera_id="cam_1",
        stream_name="stream_1",
        persistent_id="person_1",
        local_track_id="track_1",
        strategy="cnn_transformer",
        score=0.1,
        alert_level="normal",
        label="normal",
        model_name="cnn_transformer",
        sampled_at=_utc_now(),
        emitted_at=_utc_now(),
    )
    mock_conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_event_repository_persists_warning() -> None:
    from src.services.inference.event_repository import InferenceEventRepository

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    repo = InferenceEventRepository(mock_pool)
    await repo.save(
        camera_id="cam_1",
        stream_name="stream_1",
        persistent_id="person_1",
        local_track_id="track_1",
        strategy="cnn_transformer",
        score=0.65,
        alert_level="warning",
        label="warning",
        model_name="cnn_transformer",
        sampled_at=_utc_now(),
        emitted_at=_utc_now(),
    )
    mock_conn.execute.assert_called_once()


# ---------------------------------------------------------------------------
# InferenceIngressPublisher — filters unassigned tracks, crops correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inference_ingress_publisher_skips_tracks_without_persistent_id() -> None:
    from src.services.realtime_video.contracts import TrackingTrackSnapshot
    from src.services.tracking.updates import InferenceIngressPublisher

    ingress = MagicMock()
    publisher = InferenceIngressPublisher(ingress)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    track = TrackingTrackSnapshot(
        track_id="t1",
        persistent_id=None,  # no persistent id → should be skipped
        class_name="person",
        confidence=0.9,
        similarity=None,
        left=10,
        top=10,
        width=64,
        height=128,
    )
    await publisher.publish(
        camera_id="cam_1",
        stream_name="s",
        annotated_stream_name="s_ann",
        tracks=[track],
        frame=frame,
    )
    ingress.ingest_sample.assert_not_called()


@pytest.mark.asyncio
async def test_inference_ingress_publisher_enqueues_assigned_track() -> None:
    from src.services.realtime_video.contracts import TrackingTrackSnapshot
    from src.services.tracking.updates import InferenceIngressPublisher

    ingress = MagicMock()
    publisher = InferenceIngressPublisher(ingress)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    track = TrackingTrackSnapshot(
        track_id="t1",
        persistent_id="person_1",
        class_name="person",
        confidence=0.9,
        similarity=0.85,
        left=10,
        top=10,
        width=64,
        height=128,
        persistent_id_state="assigned",
        consecutive_hits=10,
        frames_since_update=0,
    )
    await publisher.publish(
        camera_id="cam_1",
        stream_name="s",
        annotated_stream_name="s_ann",
        tracks=[track],
        frame=frame,
    )
    ingress.ingest_sample.assert_called_once()
    sample: InferenceIngressSample = ingress.ingest_sample.call_args[0][0]
    assert sample.persistent_id == "person_1"
    assert sample.camera_id == "cam_1"
    assert sample.crop.shape == (128, 64, 3)


@pytest.mark.asyncio
async def test_inference_ingress_publisher_no_op_without_frame() -> None:
    from src.services.realtime_video.contracts import TrackingTrackSnapshot
    from src.services.tracking.updates import InferenceIngressPublisher

    ingress = MagicMock()
    publisher = InferenceIngressPublisher(ingress)

    track = TrackingTrackSnapshot(
        track_id="t1",
        persistent_id="person_1",
        class_name="person",
        confidence=0.9,
        similarity=None,
        left=0,
        top=0,
        width=64,
        height=128,
        persistent_id_state="assigned",
    )
    # frame=None — publisher must silently skip
    await publisher.publish(
        camera_id="cam_1",
        stream_name="s",
        annotated_stream_name="s_ann",
        tracks=[track],
        frame=None,
    )
    ingress.ingest_sample.assert_not_called()
