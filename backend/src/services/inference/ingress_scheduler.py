"""Dispatch gate and ingress queue for the inference plane."""

from __future__ import annotations

import asyncio

from src.core.logger.logger import get_logger
from src.observability.metrics import MetricsRecorder, NullMetricsRecorder
from src.services.inference.contracts import InferenceIngressSample, InferenceWorkerConfig
from src.services.inference.temporal_buffer import TemporalBufferService


class InferenceIngressScheduler:
    """Buffer incoming samples, gate dispatch, and feed the inference orchestrator.

    Dispatch gate (all conditions must be true, per plan §3.5):
      - persistent_id_state == "assigned"
      - temporal buffer depth >= window_size
      - consecutive_hits >= min_consecutive_hits
      - frames_since_update == 0
      - crop width >= min_crop_width and height >= min_crop_height
    """

    def __init__(
        self,
        config: InferenceWorkerConfig,
        buffer: TemporalBufferService,
        metrics_recorder: MetricsRecorder | None = None,
    ) -> None:
        self._config = config
        self._buffer = buffer
        self._metrics = metrics_recorder or NullMetricsRecorder()
        self._logger = get_logger(__name__)
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
        self._metrics.observe_inference_ingress_queue_depth(
            self._config.camera_id,
            self._queue.qsize(),
        )

        if not self._gate_passes(sample):
            return

        batch = self._buffer.get(sample.persistent_id)
        try:
            self._queue.put_nowait(batch)
        except asyncio.QueueFull:
            self._metrics.increment_inference_frame_drop(self._config.camera_id)
            self._logger.debug(
                "Inference ingress queue full for camera %s — dropping batch for %s",
                self._config.camera_id,
                sample.persistent_id,
            )

    def _gate_passes(self, sample: InferenceIngressSample) -> bool:
        cfg = self._config
        return (
            sample.persistent_id_state == "assigned"
            and self._buffer.depth(sample.persistent_id) >= cfg.temporal_buffer_size
            and sample.consecutive_hits >= cfg.dispatch_min_consecutive_hits
            and sample.frames_since_update == 0
            and sample.width >= cfg.dispatch_min_crop_width
            and sample.height >= cfg.dispatch_min_crop_height
        )
