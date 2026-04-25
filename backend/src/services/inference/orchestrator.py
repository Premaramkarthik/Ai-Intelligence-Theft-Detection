"""Per-camera inference orchestrator coroutine."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

import numpy as np

from src.core.logger.logger import get_logger
from src.observability.metrics import NullMetricsRecorder, PrometheusMetrics
from src.schemas.common import WebSocketEnvelope
from src.schemas.inference_events import InferenceKafkaEventPayload
from src.services.inference.batch_builder import BatchBuilder
from src.services.inference.contracts import InferenceIngressSample, InferenceWorkerConfig
from src.services.inference.decision_engine import DecisionEngine
from src.services.inference.event_repository import InferenceEventRepository
from src.services.inference.ingress_scheduler import InferenceIngressScheduler
from src.services.inference.logging import (
    log_inference_event,
    log_inference_exception,
    summarize_frame_batch,
    summarize_named_arrays,
    summarize_sample_batch,
    was_exception_logged,
)
from src.services.inference.triton_client import TritonInferenceClient
from src.services.presentation.websocket_manager import WebSocketManager


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InferenceOrchestrator:
    """Drive the end-to-end inference pipeline for one camera stream.

    Lifecycle: call ``start()`` once, ``close()`` to shut down cleanly.
    Strategy switches are applied at the next dispatch cycle; the temporal
    buffer is not flushed on switch.
    """

    def __init__(
        self,
        config: InferenceWorkerConfig,
        scheduler: InferenceIngressScheduler,
        triton: TritonInferenceClient,
        batch_builder: BatchBuilder,
        decision_engine: DecisionEngine,
        event_repository: InferenceEventRepository,
        websocket_manager: WebSocketManager,
        kafka_publisher: Any | None,
        metrics_recorder: PrometheusMetrics | NullMetricsRecorder | None = None,
        result_callback: Callable[[str, str, str, float, str], None] | None = None,
    ) -> None:
        self._config = config
        self._scheduler = scheduler
        self._triton = triton
        self._batch_builder = batch_builder
        self._decision = decision_engine
        self._repo = event_repository
        self._ws = websocket_manager
        self._kafka = kafka_publisher
        self._result_callback = result_callback
        self._logger = get_logger(__name__)
        self._prediction_logger = get_logger("src.services.inference.prediction")
        self._metrics = metrics_recorder or NullMetricsRecorder()
        self._task: asyncio.Task[None] | None = None
        self._active_tracks: set[str] = set()
        self._last_result_at: datetime | None = None
        self._healthy = True
        self._last_error: str | None = None
        self._strategy_lock = asyncio.Lock()
        self._strategy = config.strategy
        self._recent_completion_times: deque[float] = deque(maxlen=32)

    def get_snapshot_data(self) -> dict[str, object]:
        """Return a snapshot dict compatible with InferenceSnapshot fields."""

        return {
            "enabled": True,
            "strategy": self._strategy,
            "healthy": self._healthy,
            "last_error_message": self._last_error,
            "queue_depth": self._scheduler.queue.qsize(),
            "active_tracks": len(self._active_tracks),
            "last_result_at": self._last_result_at,
        }

    async def configure(
        self,
        *,
        enabled: bool | None = None,
        strategy: str | None = None,
    ) -> None:
        """Update runtime configuration. Strategy switch is lock-protected."""

        del enabled
        if strategy is not None:
            async with self._strategy_lock:
                previous_strategy = self._strategy
                self._strategy = strategy
            log_inference_event(
                self._logger,
                logging.INFO,
                "inference.strategy_switched",
                "Inference strategy switched for camera.",
                camera_id=self._config.camera_id,
                previous_strategy=previous_strategy,
                strategy=strategy,
            )

    def start(self) -> None:
        """Launch the background consume loop."""

        self._task = asyncio.create_task(self._run())
        log_inference_event(
            self._prediction_logger,
            logging.INFO,
            "inference.prediction_logger_ready",
            (
                "Prediction logging ready: "
                f"camera_id={self._config.camera_id} "
                f"strategy={self._strategy}"
            ),
            camera_id=self._config.camera_id,
            strategy=self._strategy,
        )
        log_inference_event(
            self._logger,
            logging.INFO,
            "inference.orchestrator_started",
            "Inference orchestrator started.",
            camera_id=self._config.camera_id,
            strategy=self._strategy,
        )

    async def close(self) -> None:
        """Cancel the consume loop, wait for it, and close Triton resources."""

        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            log_inference_event(
                self._logger,
                logging.INFO,
                "inference.orchestrator_stopped",
                "Inference orchestrator stopped.",
                camera_id=self._config.camera_id,
            )
        await self._triton.close()

    async def _run(self) -> None:
        queue = self._scheduler.queue
        while True:
            try:
                batch: list[InferenceIngressSample] = await queue.get()
                log_inference_event(
                    self._logger,
                    logging.DEBUG,
                    "inference.batch_dequeued",
                    "Inference batch dequeued for processing.",
                    camera_id=self._config.camera_id,
                    batch_size=len(batch),
                    queue_depth=queue.qsize(),
                )
                self._metrics.set_inference_queue_depth(
                    self._config.camera_id,
                    queue.qsize(),
                )
                await self._process_batch(batch)
            except asyncio.CancelledError:
                return
            except Exception as exc:  # pylint: disable=broad-except
                self._healthy = False
                self._last_error = str(exc)
                if was_exception_logged(exc):
                    log_inference_event(
                        self._logger,
                        logging.ERROR,
                        "inference.orchestrator_error",
                        "Inference orchestrator error.",
                        camera_id=self._config.camera_id,
                        error=str(exc),
                        error_type=exc.__class__.__name__,
                    )
                else:
                    log_inference_exception(
                        self._logger,
                        logging.ERROR,
                        "inference.orchestrator_error",
                        "Inference orchestrator error.",
                        exc,
                        camera_id=self._config.camera_id,
                    )

    async def _process_batch(self, batch: list[InferenceIngressSample]) -> None:
        if not batch:
            return

        batch_started_at = perf_counter()
        sample = batch[-1]
        async with self._strategy_lock:
            strategy = self._strategy

        model_name = _resolve_model_name(strategy)
        crops = [entry.crop for entry in batch]
        batch_summary = summarize_sample_batch(batch)
        frames_summary = summarize_frame_batch(crops)
        log_inference_event(
            self._logger,
            logging.DEBUG,
            "inference.batch_processing_started",
            "Processing inference batch.",
            camera_id=sample.camera_id,
            stream_name=sample.stream_name,
            persistent_id=sample.persistent_id,
            local_track_id=sample.local_track_id,
            strategy=strategy,
            model_name=model_name,
            queue_depth=self._scheduler.queue.qsize(),
            batch=batch_summary,
            frames=frames_summary,
        )
        log_inference_event(
            self._logger,
            logging.DEBUG,
            "inference.model_selected",
            "Selected inference model for strategy.",
            camera_id=sample.camera_id,
            strategy=strategy,
            model_name=model_name,
        )
        log_inference_event(
            self._prediction_logger,
            logging.INFO,
            "inference.prediction_request_started",
            (
                "Prediction request started: "
                f"camera_id={sample.camera_id} "
                f"local_track_id={sample.local_track_id} "
                f"persistent_id={sample.persistent_id} "
                f"strategy={strategy} "
                f"model_name={model_name} "
                f"batch_size={len(batch)}"
            ),
            camera_id=sample.camera_id,
            local_track_id=sample.local_track_id,
            persistent_id=sample.persistent_id,
            strategy=strategy,
            model_name=model_name,
            batch_size=len(batch),
        )

        if not await self._triton.ensure_connected():
            self._healthy = False
            self._last_error = f"Triton server at {self._config.triton_url} is not reachable."
            self._metrics.increment_inference_request(strategy, model_name, "triton_unavailable")
            return

        preprocessing_started_at = perf_counter()
        try:
            tensors = self._batch_builder.build(crops, strategy)
        except Exception as exc:  # pylint: disable=broad-except
            self._metrics.increment_inference_request(strategy, model_name, "preprocessing_failed")
            log_inference_exception(
                self._logger,
                logging.ERROR,
                "inference.preprocessing_failed",
                "Inference preprocessing failed.",
                exc,
                camera_id=sample.camera_id,
                stream_name=sample.stream_name,
                persistent_id=sample.persistent_id,
                local_track_id=sample.local_track_id,
                strategy=strategy,
                model_name=model_name,
                batch=batch_summary,
                frames=frames_summary,
            )
            raise

        preprocessing_latency_ms = (perf_counter() - preprocessing_started_at) * 1000.0
        self._metrics.observe_inference_preprocessing_latency(
            strategy,
            model_name,
            preprocessing_latency_ms / 1000.0,
        )
        tensor_summary = summarize_named_arrays(tensors)
        log_inference_event(
            self._logger,
            logging.DEBUG,
            "inference.preprocessing_complete",
            "Inference preprocessing completed.",
            camera_id=sample.camera_id,
            strategy=strategy,
            model_name=model_name,
            preprocessing_latency_ms=round(preprocessing_latency_ms, 3),
            tensors=tensor_summary,
        )

        inference_started_at = perf_counter()
        try:
            outputs = await self._triton.infer(model_name, tensors)
        except Exception as exc:  # pylint: disable=broad-except
            self._metrics.increment_inference_request(strategy, model_name, "execution_failed")
            if was_exception_logged(exc):
                log_inference_event(
                    self._logger,
                    logging.ERROR,
                    "inference.execution_failed",
                    "Inference execution failed.",
                    camera_id=sample.camera_id,
                    stream_name=sample.stream_name,
                    persistent_id=sample.persistent_id,
                    local_track_id=sample.local_track_id,
                    strategy=strategy,
                    model_name=model_name,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
            else:
                log_inference_exception(
                    self._logger,
                    logging.ERROR,
                    "inference.execution_failed",
                    "Inference execution failed.",
                    exc,
                    camera_id=sample.camera_id,
                    stream_name=sample.stream_name,
                    persistent_id=sample.persistent_id,
                    local_track_id=sample.local_track_id,
                    strategy=strategy,
                    model_name=model_name,
                )
            raise

        inference_latency_ms = (perf_counter() - inference_started_at) * 1000.0
        self._metrics.observe_inference_execution_latency(
            strategy,
            model_name,
            inference_latency_ms / 1000.0,
        )
        output_summary = summarize_named_arrays(outputs)
        attributions = self._score_attributions(
            batch=batch,
            outputs=outputs,
            output_summary=output_summary,
            strategy=strategy,
            model_name=model_name,
        )
        log_inference_event(
            self._prediction_logger,
            logging.INFO,
            "inference.prediction_scores_received",
            (
                "Prediction scores received: "
                f"camera_id={sample.camera_id} "
                f"strategy={strategy} "
                f"model_name={model_name} "
                f"scores={[round(score, 6) for _entry, score in attributions]}"
            ),
            camera_id=sample.camera_id,
            strategy=strategy,
            model_name=model_name,
            scores=[round(score, 6) for _entry, score in attributions],
        )
        emitted_at = _utc_now()
        payloads: list[InferenceKafkaEventPayload] = []
        for attributed_sample, score in attributions:
            alert_level = self._decision.classify(score)
            label = alert_level
            self._active_tracks.add(attributed_sample.persistent_id)
            payloads.append(
                InferenceKafkaEventPayload(
                    camera_id=attributed_sample.camera_id,
                    stream_name=attributed_sample.stream_name,
                    persistent_id=attributed_sample.persistent_id,
                    local_track_id=attributed_sample.local_track_id,
                    strategy=strategy,
                    score=score,
                    alert_level=alert_level,
                    label=label,
                    model_name=model_name,
                    sampled_at=attributed_sample.sampled_at,
                    emitted_at=emitted_at,
                )
            )
        for payload in payloads:
            self._metrics.increment_inference_result(
                strategy,
                model_name,
                payload.alert_level,
            )
            sample_age_ms = max(
                (payload.emitted_at - payload.sampled_at).total_seconds() * 1000.0,
                0.0,
            )
            prediction_message = (
                "Inference prediction emitted: "
                f"camera_id={payload.camera_id} "
                f"local_track_id={payload.local_track_id} "
                f"persistent_id={payload.persistent_id} "
                f"strategy={payload.strategy} "
                f"model_name={payload.model_name} "
                f"label={payload.label} "
                f"alert_level={payload.alert_level} "
                f"score={payload.score:.6f}"
            )
            log_inference_event(
                self._prediction_logger,
                logging.INFO,
                "inference.prediction_emitted",
                prediction_message,
                camera_id=payload.camera_id,
                stream_name=payload.stream_name,
                persistent_id=payload.persistent_id,
                local_track_id=payload.local_track_id,
                strategy=payload.strategy,
                model_name=payload.model_name,
                score=round(payload.score, 6),
                label=payload.label,
                alert_level=payload.alert_level,
                sampled_at=payload.sampled_at.isoformat(),
                emitted_at=payload.emitted_at.isoformat(),
                sample_age_ms=round(sample_age_ms, 3),
            )
        self._last_result_at = emitted_at
        self._healthy = True

        if self._result_callback is not None:
            for payload in payloads:
                self._result_callback(
                    payload.camera_id,
                    payload.local_track_id,
                    payload.label,
                    payload.score,
                    payload.alert_level,
                )

        delivery_started_at = perf_counter()
        delivery_results = await asyncio.gather(
            *(self._deliver_payload(payload) for payload in payloads),
            return_exceptions=True,
        )
        delivery_latency_ms = (perf_counter() - delivery_started_at) * 1000.0

        sink_failures: list[dict[str, str]] = []
        for payload, result in zip(payloads, delivery_results):
            if isinstance(result, Exception):
                sink_failures.append(
                    {
                        "sink": "delivery",
                        "persistent_id": payload.persistent_id,
                        "local_track_id": payload.local_track_id,
                        "error": str(result),
                        "error_type": result.__class__.__name__,
                    },
                )
            else:
                sink_failures.extend(result)
        if sink_failures:
            self._metrics.increment_inference_request(strategy, model_name, "delivery_partial_failure")
            log_inference_event(
                self._logger,
                logging.WARNING,
                "inference.delivery_failed",
                "One or more inference delivery steps failed.",
                camera_id=sample.camera_id,
                stream_name=sample.stream_name,
                persistent_id=sample.persistent_id,
                local_track_id=sample.local_track_id,
                strategy=strategy,
                model_name=model_name,
                sink_failures=sink_failures,
            )

        completed_at = perf_counter()
        total_latency_ms = (completed_at - batch_started_at) * 1000.0
        sample_age_ms = max(
            (
                (emitted_at - payload.sampled_at).total_seconds() * 1000.0
                for payload in payloads
            ),
            default=0.0,
        )
        inference_request_fps = self._record_completion(completed_at)
        representative_payload = payloads[-1]
        self._metrics.observe_inference_total_latency(
            strategy,
            model_name,
            total_latency_ms / 1000.0,
        )
        self._metrics.observe_inference_sample_age(
            strategy,
            model_name,
            sample_age_ms / 1000.0,
        )
        self._metrics.increment_inference_request(strategy, model_name, "success")
        log_inference_event(
            self._logger,
            logging.INFO,
            "inference.completed",
            "Inference batch completed.",
            camera_id=sample.camera_id,
            stream_name=sample.stream_name,
            persistent_id=sample.persistent_id,
            local_track_id=sample.local_track_id,
            strategy=strategy,
            model_name=model_name,
            batch_size=len(batch),
            emitted_results=len(payloads),
            active_tracks=len(self._active_tracks),
            preprocessing_latency_ms=round(preprocessing_latency_ms, 3),
            inference_latency_ms=round(inference_latency_ms, 3),
            delivery_latency_ms=round(delivery_latency_ms, 3),
            total_latency_ms=round(total_latency_ms, 3),
            sample_age_ms=round(sample_age_ms, 3),
            inference_request_fps=round(inference_request_fps, 3),
            score=representative_payload.score,
            alert_level=representative_payload.alert_level,
            label=representative_payload.label,
            scores=[round(payload.score, 6) for payload in payloads],
            alert_levels=[payload.alert_level for payload in payloads],
            outputs=output_summary,
            sink_failures=sink_failures,
        )
        self._metrics.set_inference_queue_depth(
            self._config.camera_id,
            self._scheduler.queue.qsize(),
        )

    def _score_attributions(
        self,
        *,
        batch: list[InferenceIngressSample],
        outputs: dict[str, np.ndarray],
        output_summary: dict[str, dict[str, object]],
        strategy: str,
        model_name: str,
    ) -> list[tuple[InferenceIngressSample, float]]:
        """Map Triton output scores back to the samples they describe."""

        sample = batch[-1]
        output_tensor_name = _resolve_output_tensor_name(strategy)
        if output_tensor_name not in outputs:
            log_inference_event(
                self._logger,
                logging.WARNING,
                "inference.output_missing",
                "Inference response missing expected output tensor.",
                camera_id=sample.camera_id,
                strategy=strategy,
                model_name=model_name,
                expected_output_tensor=output_tensor_name,
                outputs=output_summary,
            )
            return [(sample, 0.0)]

        raw_tensor = outputs[output_tensor_name]
        log_inference_event(
            self._prediction_logger,
            logging.INFO,
            "inference.raw_logits",
            (
                "Raw Triton logits received: "
                f"camera_id={sample.camera_id} "
                f"strategy={strategy} "
                f"model_name={model_name} "
                f"logits={np.asarray(raw_tensor).reshape(-1).tolist()}"
            ),
            camera_id=sample.camera_id,
            strategy=strategy,
            model_name=model_name,
            logits=np.asarray(raw_tensor).reshape(-1).tolist(),
        )

        if strategy == "vjepa_probe":
            score = _extract_vjepa_score(raw_tensor)
            return [(sample, score)]

        try:
            scores = _extract_scalar_scores(raw_tensor, expected_count=len(batch))
        except Exception as exc:  # pylint: disable=broad-except
            log_inference_exception(
                self._logger,
                logging.ERROR,
                "inference.output_parse_failed",
                "Failed to parse inference output tensor.",
                exc,
                camera_id=sample.camera_id,
                strategy=strategy,
                model_name=model_name,
                outputs=output_summary,
            )
            raise

        if len(scores) == 1:
            return [(sample, scores[0])]
        return list(zip(batch, scores))

    async def _deliver_payload(self, payload: InferenceKafkaEventPayload) -> list[dict[str, str]]:
        task_specs: list[tuple[str, Any]] = [
            ("websocket", self._broadcast_ws(payload)),
            ("kafka", self._publish_kafka(payload)),
        ]
        if payload.alert_level != "normal":
            task_specs.append(("persistence", self._persist(payload)))
        results = await asyncio.gather(
            *(
                self._timed_delivery(sink_name, coroutine)
                for sink_name, coroutine in task_specs
            ),
            return_exceptions=True,
        )
        sink_failures: list[dict[str, str]] = []
        for (sink_name, _), result in zip(task_specs, results):
            if isinstance(result, Exception):
                sink_failures.append(
                    {
                        "sink": sink_name,
                        "persistent_id": payload.persistent_id,
                        "local_track_id": payload.local_track_id,
                        "error": str(result),
                        "error_type": result.__class__.__name__,
                    },
                )
        return sink_failures

    async def _timed_delivery(self, sink_name: str, coroutine: Any) -> None:
        started_at = perf_counter()
        try:
            await coroutine
        finally:
            self._metrics.observe_inference_delivery_latency(
                sink_name,
                perf_counter() - started_at,
            )

    async def _broadcast_ws(self, payload: InferenceKafkaEventPayload) -> None:
        envelope = WebSocketEnvelope(
            type=payload.event,
            topic="inference",
            message="Inference result.",
            camera_id=payload.camera_id,
            data=payload.model_dump(mode="json"),
        )
        await self._ws.broadcast(envelope)
        if payload.alert_level != "normal":
            alert_envelope = WebSocketEnvelope(
                type="inference.alert",
                topic="inference",
                message="Inference alert.",
                camera_id=payload.camera_id,
                data={
                    "alert_level": payload.alert_level,
                    "persistent_id": payload.persistent_id,
                    "camera_id": payload.camera_id,
                    "score": payload.score,
                    "strategy": payload.strategy,
                },
            )
            await self._ws.broadcast(alert_envelope)

    async def _publish_kafka(self, payload: InferenceKafkaEventPayload) -> None:
        if self._kafka is None:
            return
        try:
            await self._kafka.publish(payload.model_dump(mode="json"))
        except Exception as exc:  # pylint: disable=broad-except
            log_inference_event(
                self._logger,
                logging.WARNING,
                "inference.kafka_publish_failed",
                "Kafka inference publish failed.",
                camera_id=self._config.camera_id,
                persistent_id=payload.persistent_id,
                local_track_id=payload.local_track_id,
                strategy=payload.strategy,
                model_name=payload.model_name,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )

    async def _persist(self, payload: InferenceKafkaEventPayload) -> None:
        await self._repo.save(
            camera_id=payload.camera_id,
            stream_name=payload.stream_name,
            persistent_id=payload.persistent_id,
            local_track_id=payload.local_track_id,
            strategy=payload.strategy,
            score=payload.score,
            alert_level=payload.alert_level,
            label=payload.label,
            model_name=payload.model_name,
            sampled_at=payload.sampled_at,
            emitted_at=payload.emitted_at,
        )

    def _record_completion(self, completed_at: float) -> float:
        self._recent_completion_times.append(completed_at)
        if len(self._recent_completion_times) < 2:
            return 0.0
        elapsed = self._recent_completion_times[-1] - self._recent_completion_times[0]
        if elapsed <= 0.0:
            return 0.0
        return (len(self._recent_completion_times) - 1) / elapsed


def _extract_scalar_scores(output: np.ndarray, *, expected_count: int) -> list[float]:
    """Return scalar scores from a Triton output tensor without guessing labels."""

    array = np.asarray(output)
    flattened = array.reshape(-1)
    if flattened.size == 1:
        return [float(flattened[0])]
    if flattened.size == expected_count:
        return [float(value) for value in flattened]
    raise ValueError(
        "Expected Triton output tensor 'output' to contain either one scalar score "
        f"or {expected_count} scalar scores; got shape={list(array.shape)}."
    )


def _extract_vjepa_score(logits: np.ndarray) -> float:
    """Softmax over 2-class VJEPA logits; return class-1 (shoplifter) probability."""

    array = np.asarray(logits).reshape(-1)
    if array.size != 2:
        return float(array.flat[0])
    shifted = array - array.max()
    exp_shifted = np.exp(shifted)
    return float(exp_shifted[1] / exp_shifted.sum())


def _resolve_model_name(strategy: str) -> str:
    """Map worker strategy names onto Triton repository model names."""

    if strategy == "vjepa_probe":
        return "vjepa_finetune"
    return strategy


def _resolve_output_tensor_name(strategy: str) -> str:
    """Return the expected Triton output tensor for the selected strategy."""

    if strategy == "vjepa_probe":
        return "logits"
    return "output"
