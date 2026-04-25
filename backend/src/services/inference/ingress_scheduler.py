"""Dispatch gate and ingress queue for the inference plane."""

from __future__ import annotations

import asyncio
import logging

from src.core.logger.logger import get_logger
from src.observability.metrics import NullMetricsRecorder, PrometheusMetrics
from src.services.inference.contracts import InferenceIngressSample, InferenceWorkerConfig
from src.services.inference.logging import log_inference_event, summarize_sample
from src.services.inference.temporal_buffer import TemporalBufferService


class InferenceIngressScheduler:
    """Buffer incoming samples, gate dispatch, and feed the inference orchestrator.

    Dispatch gate (all conditions must be true, per plan section 3.5):
      - temporal buffer depth >= window_size
      - consecutive_hits >= min_consecutive_hits
      - frames_since_update == 0
      - crop width >= min_crop_width and height >= min_crop_height

    Short temporal windows are padded later by ``BatchBuilder`` so inference can
    begin on the earliest visible person track.
    """

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
        self._queue: asyncio.Queue[list[InferenceIngressSample]] = asyncio.Queue(
            maxsize=config.ingress_queue_maxsize,
        )

    @property
    def queue(self) -> asyncio.Queue[list[InferenceIngressSample]]:
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

        batch = self._buffer.get(sample.persistent_id)
        try:
            self._queue.put_nowait(batch)
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
        if current_buffer_depth < cfg.temporal_buffer_size:
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
