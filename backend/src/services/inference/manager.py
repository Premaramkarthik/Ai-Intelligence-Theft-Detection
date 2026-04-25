"""Lifecycle manager for per-camera inference orchestrators."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from src.core.logger.logger import get_logger
from src.observability.metrics import NullMetricsRecorder, PrometheusMetrics
from src.services.inference.batch_builder import BatchBuilder
from src.services.inference.contracts import (
    InferenceIngressSample,
    InferenceSnapshot,
    InferenceWorkerConfig,
)
from src.services.inference.decision_engine import DecisionEngine
from src.services.inference.event_repository import InferenceEventRepository
from src.services.inference.ingress_scheduler import InferenceIngressScheduler
from src.services.inference.logging import log_inference_event
from src.services.inference.orchestrator import InferenceOrchestrator
from src.services.inference.temporal_buffer import TemporalBufferService
from src.services.inference.triton_client import TritonInferenceClient
from src.services.presentation.websocket_manager import WebSocketManager


class InferenceManager:
    """Manage the lifecycle of per-camera ``InferenceOrchestrator`` instances.

    Mirrors ``TrackingStreamManager``: cameras are opted in via
    ``configure_stream(enabled=True)`` or when ``PATCH /streams/{id}/inference``
    is called. Tracking always runs regardless of inference state.
    """

    def __init__(
        self,
        event_repository: InferenceEventRepository,
        websocket_manager: WebSocketManager,
        kafka_publisher: Any | None,
        metrics_recorder: PrometheusMetrics | NullMetricsRecorder | None = None,
        triton_url: str = "localhost:8001",
        triton_max_in_flight: int = 8,
        triton_reconnect_interval_seconds: float = 5.0,
    ) -> None:
        self._event_repository = event_repository
        self._websocket_manager = websocket_manager
        self._kafka_publisher = kafka_publisher
        self._triton_url = triton_url
        self._triton_max_in_flight = triton_max_in_flight
        self._triton_reconnect_interval_seconds = triton_reconnect_interval_seconds
        self._logger = get_logger(__name__)
        self._metrics_recorder = metrics_recorder or NullMetricsRecorder()
        self._orchestrators: dict[str, InferenceOrchestrator] = {}
        self._schedulers: dict[str, InferenceIngressScheduler] = {}
        self._result_callback: Callable[[str, str, str, float, str], None] | None = None

    # ------------------------------------------------------------------
    # Ingress - called by InferenceIngressPublisher from the event loop
    # ------------------------------------------------------------------

    def set_result_callback(
        self, callback: Callable[[str, str, str, float, str], None]
    ) -> None:
        """Register a callback invoked for each inference result.

        Signature: callback(camera_id, local_track_id, label, score, alert_level)
        Applied to all subsequently created orchestrators; existing ones are not updated.
        """
        self._result_callback = callback

    def ingest_sample(self, sample: InferenceIngressSample) -> None:
        """Route one tracking crop to the camera's scheduler, if active."""

        scheduler = self._schedulers.get(sample.camera_id)
        if scheduler is not None:
            scheduler.ingest(sample)
            return
        log_inference_event(
            self._logger,
            logging.DEBUG,
            "inference.ingress_ignored",
            "Inference sample ignored because the camera has no active scheduler.",
            camera_id=sample.camera_id,
            stream_name=sample.stream_name,
            local_track_id=sample.local_track_id,
            persistent_id=sample.persistent_id,
        )

    # ------------------------------------------------------------------
    # Control plane - called by PATCH /streams/{camera_id}/inference
    # ------------------------------------------------------------------

    async def configure_stream(
        self,
        camera_id: str,
        *,
        enabled: bool | None = None,
        strategy: str | None = None,
    ) -> None:
        """Start, stop, or reconfigure inference for one camera.

        - ``enabled=True``  - starts the orchestrator (no-op if already running).
        - ``enabled=False`` - stops and removes the orchestrator.
        - ``strategy``      - live strategy switch; buffer is not flushed.
        """

        if enabled is True and camera_id not in self._orchestrators:
            await self._start_camera(camera_id, strategy or "vjepa_probe")
        elif enabled is False:
            await self.remove_camera(camera_id)
        elif strategy is not None and camera_id in self._orchestrators:
            await self._orchestrators[camera_id].configure(strategy=strategy)

    # ------------------------------------------------------------------
    # State inspection
    # ------------------------------------------------------------------

    def get_snapshot(self, camera_id: str) -> InferenceSnapshot | None:
        """Return the current ``InferenceSnapshot`` for a camera, or ``None``."""

        orchestrator = self._orchestrators.get(camera_id)
        if orchestrator is None:
            return None
        data = orchestrator.get_snapshot_data()
        return InferenceSnapshot(camera_id=camera_id, **data)

    def is_camera_enabled(self, camera_id: str) -> bool:
        """Return ``True`` when a camera currently has an active scheduler."""

        return camera_id in self._schedulers

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Stop all running orchestrators and release Triton connections."""

        for camera_id in list(self._orchestrators):
            await self._stop_camera(camera_id)

    async def remove_camera(self, camera_id: str) -> None:
        """Stop inference and discard scheduler/orchestrator state for one camera."""

        await self._stop_camera(camera_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _start_camera(self, camera_id: str, strategy: str) -> None:
        config = InferenceWorkerConfig(
            camera_id=camera_id,
            strategy=strategy,
            triton_url=self._triton_url,
            triton_max_in_flight=self._triton_max_in_flight,
            triton_reconnect_interval_seconds=self._triton_reconnect_interval_seconds,
        )
        buffer = TemporalBufferService(
            window_size=config.temporal_buffer_size,
            gap_reset_seconds=config.identity_gap_reset_seconds,
        )
        scheduler = InferenceIngressScheduler(
            config,
            buffer,
            metrics_recorder=self._metrics_recorder,
        )
        triton = TritonInferenceClient(
            url=config.triton_url,
            max_in_flight=config.triton_max_in_flight,
            reconnect_interval_seconds=config.triton_reconnect_interval_seconds,
            metrics_recorder=self._metrics_recorder,
        )
        try:
            await triton.connect()
        except Exception as exc:  # pylint: disable=broad-except
            log_inference_event(
                self._logger,
                logging.WARNING,
                "inference.triton_connect_failed",
                "Triton connection failed; inference will stay idle and retry automatically until Triton is reachable.",
                camera_id=camera_id,
                strategy=strategy,
                triton_url=config.triton_url,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )

        orchestrator = InferenceOrchestrator(
            config=config,
            scheduler=scheduler,
            triton=triton,
            batch_builder=BatchBuilder(),
            decision_engine=DecisionEngine(config),
            event_repository=self._event_repository,
            websocket_manager=self._websocket_manager,
            kafka_publisher=self._kafka_publisher,
            metrics_recorder=self._metrics_recorder,
            result_callback=self._result_callback,
        )
        self._schedulers[camera_id] = scheduler
        self._orchestrators[camera_id] = orchestrator
        self._metrics_recorder.set_inference_queue_depth(camera_id, 0)
        orchestrator.start()
        log_inference_event(
            self._logger,
            logging.INFO,
            "inference.camera_started",
            "Inference started for camera.",
            camera_id=camera_id,
            strategy=strategy,
            triton_url=config.triton_url,
            triton_max_in_flight=config.triton_max_in_flight,
            temporal_buffer_size=config.temporal_buffer_size,
            ingress_queue_maxsize=config.ingress_queue_maxsize,
        )

    async def _stop_camera(self, camera_id: str) -> None:
        orchestrator = self._orchestrators.pop(camera_id, None)
        self._schedulers.pop(camera_id, None)
        if orchestrator is not None:
            try:
                await orchestrator.close()
            except Exception as exc:  # pylint: disable=broad-except
                log_inference_event(
                    self._logger,
                    logging.WARNING,
                    "inference.camera_stop_failed",
                    "Inference camera cleanup failed.",
                    camera_id=camera_id,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
            log_inference_event(
                self._logger,
                logging.INFO,
                "inference.camera_stopped",
                "Inference stopped for camera.",
                camera_id=camera_id,
            )
        self._metrics_recorder.set_inference_queue_depth(camera_id, 0)
