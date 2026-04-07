"""Per-camera inference orchestrator coroutine."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from src.core.logger.logger import get_logger
from src.observability.metrics import MetricsRecorder, NullMetricsRecorder
from src.schemas.common import WebSocketEnvelope
from src.schemas.inference_events import InferenceKafkaEventPayload
from src.services.inference.batch_builder import BatchBuilder
from src.services.inference.contracts import InferenceIngressSample, InferenceWorkerConfig
from src.services.inference.decision_engine import DecisionEngine
from src.services.inference.event_repository import InferenceEventRepository
from src.services.inference.ingress_scheduler import InferenceIngressScheduler
from src.services.inference.triton_client import TritonInferenceClient
from src.services.presentation.websocket_manager import WebSocketManager
from src.services.tracking_kafka.service import _InferenceKafkaPublisher


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InferenceOrchestrator:
    """Drive the end-to-end inference pipeline for one camera stream.

    Lifecycle: call ``start()`` once, ``close()`` to shut down cleanly.
    Strategy switches are applied at the next dispatch cycle — the temporal
    buffer is NOT flushed on switch (plan §3.4).
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
        kafka_publisher: _InferenceKafkaPublisher | None,
        metrics_recorder: MetricsRecorder | None = None,
    ) -> None:
        self._config = config
        self._scheduler = scheduler
        self._triton = triton
        self._batch_builder = batch_builder
        self._decision = decision_engine
        self._repo = event_repository
        self._ws = websocket_manager
        self._kafka = kafka_publisher
        self._metrics = metrics_recorder or NullMetricsRecorder()
        self._logger = get_logger(__name__)
        self._task: asyncio.Task[None] | None = None
        self._active_tracks: set[str] = set()
        self._last_result_at: datetime | None = None
        self._healthy = True
        self._last_error: str | None = None
        # Strategy may be updated at runtime; use a lock to avoid data races.
        self._strategy_lock = asyncio.Lock()
        self._strategy = config.strategy

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
        """Update runtime configuration.  Strategy switch is lock-protected."""
        if strategy is not None:
            async with self._strategy_lock:
                self._strategy = strategy
                self._logger.info(
                    "Inference strategy for camera %s switched to %s",
                    self._config.camera_id,
                    strategy,
                )

    def start(self) -> None:
        """Launch the background consume loop."""
        self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        """Cancel the consume loop and wait for it to finish."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        queue = self._scheduler.queue
        while True:
            try:
                batch: list[InferenceIngressSample] = await queue.get()
                await self._process_batch(batch)
            except asyncio.CancelledError:
                return
            except Exception as exc:  # pylint: disable=broad-except
                self._healthy = False
                self._last_error = str(exc)
                self._logger.exception(
                    "Inference orchestrator error for camera %s: %s",
                    self._config.camera_id,
                    exc,
                )

    async def _process_batch(self, batch: list[InferenceIngressSample]) -> None:
        if not batch:
            return

        sample = batch[-1]  # latest sample carries the most recent metadata
        async with self._strategy_lock:
            strategy = self._strategy

        model_name = strategy
        crops = [s.crop for s in batch]
        tensors = self._batch_builder.build(crops, strategy)

        outputs = await self._triton.infer(model_name, tensors)
        score = float(outputs["output"].flat[0]) if "output" in outputs else 0.0
        alert_level = self._decision.classify(score)
        label = alert_level
        emitted_at = _utc_now()

        self._active_tracks.add(sample.persistent_id)
        self._last_result_at = emitted_at
        self._healthy = True

        payload = InferenceKafkaEventPayload(
            camera_id=sample.camera_id,
            stream_name=sample.stream_name,
            persistent_id=sample.persistent_id,
            local_track_id=sample.local_track_id,
            strategy=strategy,
            score=score,
            alert_level=alert_level,
            label=label,
            model_name=model_name,
            sampled_at=sample.sampled_at,
            emitted_at=emitted_at,
        )

        tasks = [self._broadcast_ws(payload), self._publish_kafka(payload)]
        if alert_level != "normal":
            tasks.append(self._persist(payload))
        await asyncio.gather(*tasks, return_exceptions=True)

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
            self._logger.warning(
                "Kafka inference publish failed for camera %s: %s",
                self._config.camera_id,
                exc,
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
