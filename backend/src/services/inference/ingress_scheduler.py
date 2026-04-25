"""Dispatch gate and ingress queue for the inference plane."""

from __future__ import annotations

import asyncio
import logging
from time import monotonic

from src.core.logger.logger import get_logger
from src.observability.metrics import NullMetricsRecorder, PrometheusMetrics
from src.services.inference.contracts import InferenceIngressSample, InferenceWorkerConfig
from src.services.inference.logging import log_inference_event, summarize_sample
from src.services.inference.temporal_buffer import TemporalBufferService


class _LatestOnlyQueue:
    """Latest-only queue for inference batches.

    For each persistent_id only the most recent batch is retained.  When a new
    batch arrives before the orchestrator consumes the previous one, the old
    batch is silently replaced so the model always sees the freshest crops.
    The external interface (``get``, ``qsize``) mirrors ``asyncio.Queue`` so the
    orchestrator needs no changes.
    """

    def __init__(self, maxsize: int = 0) -> None:
        self._latest: dict[str, list[InferenceIngressSample]] = {}
        self._queued: set[str] = set()
        self._notify: asyncio.Queue[str] = asyncio.Queue(maxsize=maxsize)

    def qsize(self) -> int:
        return self._notify.qsize()

    def full(self) -> bool:
        return self._notify.full()

    def put_latest(self, persistent_id: str, batch: list[InferenceIngressSample]) -> None:
        """Replace (or register) the latest batch for a track.

        Raises ``asyncio.QueueFull`` only when a *new* track would exceed
        ``maxsize`` — updates to an already-queued track are always free.
        """
        self._latest[persistent_id] = batch
        if persistent_id not in self._queued:
            self._notify.put_nowait(persistent_id)  # raises QueueFull if at capacity
            self._queued.add(persistent_id)

    async def get(self) -> list[InferenceIngressSample]:
        while True:
            pid = await self._notify.get()
            self._queued.discard(pid)
            batch = self._latest.pop(pid, None)
            if batch is not None:
                return batch


class InferenceIngressScheduler:
    """Buffer incoming samples, gate dispatch, and feed the inference orchestrator.

    Dispatch gate (all conditions must be true, per plan section 3.5):
      - temporal buffer depth >= dispatch_min_temporal_frames
      - consecutive_hits >= min_consecutive_hits
      - frames_since_update == 0
      - crop width >= min_crop_width and height >= min_crop_height

    Short temporal windows are padded later by ``BatchBuilder`` so inference can
    begin on the earliest visible person track.
    """

    _VISIBLE_LOG_INTERVAL_SECONDS = 30.0

    def __init__(
        self,
        config: InferenceWorkerConfig,
        buffer: TemporalBufferService,
        *,
        metrics_recorder: PrometheusMetrics | NullMetricsRecorder | None = None,
    ) -> None:
        self._config = config
        self._buffer = buffer
        self._logger = get_logger(__name__)
        self._metrics_recorder = metrics_recorder or NullMetricsRecorder()
        self._queue: _LatestOnlyQueue = _LatestOnlyQueue(
            maxsize=config.ingress_queue_maxsize,
        )
        self._last_enqueued_at: dict[str, float] = {}
        self._last_visible_state: tuple[str, float] | None = None

    @property
    def queue(self) -> _LatestOnlyQueue:
        """Expose the dispatch queue for the orchestrator to consume."""

        return self._queue

    def ingest(self, sample: InferenceIngressSample) -> None:
        """Push a sample through the gate; enqueue a dispatch batch when gate passes."""

        self._buffer.push(sample)
        queue_depth_before = self._queue.qsize()
        temporal_buffer_depth = self._buffer.depth(sample.persistent_id)
        log_inference_event(
            self._logger,
            logging.DEBUG,
            "inference.ingress_received",
            "Inference ingress sample received.",
            camera_id=self._config.camera_id,
            queue_depth=queue_depth_before,
            temporal_buffer_depth=temporal_buffer_depth,
            sample=summarize_sample(sample),
        )

        gate_failure_reasons = self._gate_failure_reasons(sample, temporal_buffer_depth)
        if gate_failure_reasons:
            self._log_visible_state(
                state=f"gate:{'|'.join(gate_failure_reasons)}",
                event="inference.gate_rejected_visible",
                message=(
                    "Inference dispatch gate rejected sample: "
                    f"camera_id={self._config.camera_id} "
                    f"persistent_id={sample.persistent_id} "
                    f"local_track_id={sample.local_track_id} "
                    f"failure_reasons={gate_failure_reasons} "
                    f"queue_depth={queue_depth_before} "
                    f"temporal_buffer_depth={temporal_buffer_depth} "
                    f"crop={sample.width}x{sample.height} "
                    f"consecutive_hits={sample.consecutive_hits} "
                    f"frames_since_update={sample.frames_since_update}"
                ),
                camera_id=self._config.camera_id,
                queue_depth=queue_depth_before,
                temporal_buffer_depth=temporal_buffer_depth,
                failure_reasons=gate_failure_reasons,
                sample=summarize_sample(sample),
            )
            log_inference_event(
                self._logger,
                logging.DEBUG,
                "inference.gate_rejected",
                "Inference dispatch gate rejected sample.",
                camera_id=self._config.camera_id,
                queue_depth=queue_depth_before,
                temporal_buffer_depth=temporal_buffer_depth,
                failure_reasons=gate_failure_reasons,
                sample=summarize_sample(sample),
            )
            for reason in gate_failure_reasons:
                self._metrics_recorder.increment_inference_gate_rejection(
                    self._config.camera_id,
                    reason,
                )
            self._metrics_recorder.set_inference_queue_depth(
                self._config.camera_id,
                self._queue.qsize(),
            )
            return

        # Per-person cooldown: skip if the same person was enqueued within the cooldown window.
        cooldown = self._config.dispatch_cooldown_seconds
        if cooldown > 0:
            last = self._last_enqueued_at.get(sample.persistent_id)
            now_mono = monotonic()
            if last is not None and (now_mono - last) < cooldown:
                self._metrics_recorder.set_inference_queue_depth(
                    self._config.camera_id,
                    self._queue.qsize(),
                )
                return
            self._last_enqueued_at[sample.persistent_id] = now_mono

        batch = self._buffer.get(sample.persistent_id)
        try:
            self._queue.put_latest(sample.persistent_id, batch)
        except asyncio.QueueFull:
            self._metrics_recorder.increment_inference_queue_full(self._config.camera_id)
            self._metrics_recorder.increment_inference_frame_drop(
                self._config.camera_id,
                reason="queue_full",
            )
            log_inference_event(
                self._logger,
                logging.WARNING,
                "inference.queue_full",
                "Inference ingress queue full; dropping batch.",
                camera_id=self._config.camera_id,
                persistent_id=sample.persistent_id,
                queue_depth=self._queue.qsize(),
                batch_size=len(batch),
            )
            self._metrics_recorder.set_inference_queue_depth(
                self._config.camera_id,
                self._queue.qsize(),
            )
            return

        queue_depth_after = self._queue.qsize()
        self._metrics_recorder.set_inference_queue_depth(
            self._config.camera_id,
            queue_depth_after,
        )
        self._log_visible_state(
            state="enqueued",
            event="inference.batch_enqueued_visible",
            message=(
                "Inference batch enqueued for orchestration: "
                f"camera_id={self._config.camera_id} "
                f"persistent_id={sample.persistent_id} "
                f"local_track_id={sample.local_track_id} "
                f"batch_size={len(batch)} "
                f"queue_depth={queue_depth_after} "
                f"temporal_buffer_depth={temporal_buffer_depth}"
            ),
            camera_id=self._config.camera_id,
            persistent_id=sample.persistent_id,
            batch_size=len(batch),
            queue_depth=queue_depth_after,
            temporal_buffer_depth=temporal_buffer_depth,
        )
        log_inference_event(
            self._logger,
            logging.DEBUG,
            "inference.batch_enqueued",
            "Inference batch enqueued for orchestration.",
            camera_id=self._config.camera_id,
            persistent_id=sample.persistent_id,
            batch_size=len(batch),
            queue_depth=queue_depth_after,
            temporal_buffer_depth=temporal_buffer_depth,
        )

    def _log_visible_state(
        self,
        *,
        state: str,
        event: str,
        message: str,
        **fields: object,
    ) -> None:
        now = monotonic()
        if self._last_visible_state is not None:
            previous_state, previous_logged_at = self._last_visible_state
            if previous_state == state and (
                now - previous_logged_at < self._VISIBLE_LOG_INTERVAL_SECONDS
            ):
                return
        self._last_visible_state = (state, now)
        log_inference_event(
            self._logger,
            logging.INFO,
            event,
            message,
            **fields,
        )

    def _gate_passes(self, sample: InferenceIngressSample) -> bool:
        return not self._gate_failure_reasons(sample)

    def _gate_failure_reasons(
        self,
        sample: InferenceIngressSample,
        buffer_depth: int | None = None,
    ) -> list[str]:
        cfg = self._config
        current_buffer_depth = (
            buffer_depth
            if buffer_depth is not None
            else self._buffer.depth(sample.persistent_id)
        )
        reasons: list[str] = []
        if current_buffer_depth < cfg.dispatch_min_temporal_frames:
            reasons.append("temporal_buffer_not_ready")
        if sample.consecutive_hits < cfg.dispatch_min_consecutive_hits:
            reasons.append("insufficient_consecutive_hits")
        if sample.frames_since_update != 0:
            reasons.append("stale_track_frame")
        if sample.width < cfg.dispatch_min_crop_width:
            reasons.append("crop_width_below_threshold")
        if sample.height < cfg.dispatch_min_crop_height:
            reasons.append("crop_height_below_threshold")
        return reasons
