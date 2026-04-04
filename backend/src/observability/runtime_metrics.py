"""Periodic runtime metric collection from long-lived backend services."""

# pylint: disable=too-many-instance-attributes

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from src.observability.metrics import MetricsRecorder
from src.services.realtime_video.mediamtx_service import MediaMtxService
from src.services.realtime_video.stream_manager import MediaMtxStreamManager, WorkerSnapshot
from src.services.stream.kafka_event_consumer import StreamEventConsumer
from src.services.tracking.manager import (
    TrackingRuntimeSnapshot,
    TrackingStreamManager,
)
from src.services.tracking_kafka.service import TrackingKafkaProducerService


@dataclass(slots=True)
class RuntimeMetricsDependencies:
    """Services whose runtime state is exported as Prometheus metrics."""

    stream_manager: MediaMtxStreamManager
    tracking_manager: TrackingStreamManager
    tracking_kafka_producer: TrackingKafkaProducerService
    kafka_consumer: StreamEventConsumer
    mediamtx_service: MediaMtxService


class RuntimeMetricsCollector:
    """Collect metrics from runtime managers without disturbing hot paths."""

    def __init__(
        self,
        metrics: MetricsRecorder,
        dependencies: RuntimeMetricsDependencies,
        interval_seconds: float = 5.0,
    ) -> None:
        self._metrics = metrics
        self._dependencies = dependencies
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._known_stream_cameras: set[str] = set()
        self._known_tracking_cameras: set[str] = set()
        self._known_tracking_cameras: set[str] = set()
        self._last_stream_decoded_frames: dict[str, int] = {}
        self._last_tracking_processed_frames: dict[str, int] = {}
        self._last_tracking_published_frames: dict[str, int] = {}

    async def start(self) -> None:
        """Start the periodic runtime metrics task if it is not already running."""

        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the periodic runtime metrics task."""

        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def collect_once(self) -> None:
        """Collect and publish one runtime snapshot."""

        self._collect_stream_worker_metrics()
        self._collect_tracking_worker_metrics()
        await self._collect_dependency_health()

    async def _run_loop(self) -> None:
        """Collect runtime metrics until the collector is stopped."""

        while True:
            await self.collect_once()
            await asyncio.sleep(self._interval_seconds)

    def _collect_stream_worker_metrics(self) -> None:
        manager = self._dependencies.stream_manager
        active_cameras = set(manager.active_cameras())
        self._known_stream_cameras.update(active_cameras)
        self._metrics.set_stream_worker_count(manager.active_worker_count())
        for camera_id in sorted(self._known_stream_cameras):
            snapshot = manager.get_snapshot(camera_id)
            self._publish_stream_snapshot(camera_id, snapshot)

    def _collect_tracking_worker_metrics(self) -> None:
        manager = self._dependencies.tracking_manager
        active_cameras = set(manager.active_cameras())
        self._known_tracking_cameras.update(active_cameras)
        self._metrics.set_tracking_worker_count(manager.active_worker_count())
        for camera_id in sorted(self._known_tracking_cameras):
            snapshot = manager.get_runtime_snapshot(camera_id)
            self._publish_tracking_snapshot(camera_id, snapshot)

    async def _collect_dependency_health(self) -> None:
        self._metrics.set_dependency_health(
            "kafka_consumer",
            bool(self._dependencies.kafka_consumer.health_snapshot()["healthy"]),
        )
        self._metrics.set_dependency_health(
            "tracking_kafka_producer",
            bool(self._dependencies.tracking_kafka_producer.health_snapshot()["healthy"]),
        )
        mediamtx_snapshot = self._dependencies.mediamtx_service.health_snapshot()
        self._metrics.set_dependency_health("mediamtx", bool(mediamtx_snapshot.healthy))

    def _publish_stream_snapshot(self, camera_id: str, snapshot: WorkerSnapshot) -> None:
        self._metrics.set_stream_worker_up(camera_id, snapshot.is_process_alive)
        self._metrics.set_stream_reconnect_attempts(camera_id, snapshot.reconnect_attempts)
        self._metrics.set_stream_current_fps(camera_id, snapshot.current_fps)
        self._metrics.set_stream_queue_latency_ms(camera_id, snapshot.queue_latency_ms)
        self._metrics.set_stream_decode_time_ms(camera_id, snapshot.decode_time_ms)
        self._metrics.set_stream_last_frame_age_seconds(
            camera_id,
            _age_seconds(snapshot.last_frame_at),
        )

        previous_decoded_frames = self._last_stream_decoded_frames.get(camera_id, 0)
        decoded_delta = max(snapshot.decoded_frames - previous_decoded_frames, 0)
        self._metrics.increment_stream_decoded_frames(camera_id, decoded_delta)
        self._last_stream_decoded_frames[camera_id] = snapshot.decoded_frames

    def _publish_tracking_snapshot(
        self,
        camera_id: str,
        snapshot: TrackingRuntimeSnapshot,
    ) -> None:
        self._metrics.set_tracking_worker_up(camera_id, snapshot.is_process_alive)
        self._metrics.set_tracking_reconnect_attempts(camera_id, snapshot.reconnect_attempts)
        self._metrics.set_tracking_active_tracks(camera_id, snapshot.active_tracks)
        self._metrics.set_tracking_last_frame_age_seconds(
            camera_id,
            _age_seconds(snapshot.last_frame_at),
        )

        previous_processed_frames = self._last_tracking_processed_frames.get(camera_id, 0)
        processed_delta = max(snapshot.processed_frames - previous_processed_frames, 0)
        self._metrics.increment_tracking_processed_frames(camera_id, processed_delta)
        self._last_tracking_processed_frames[camera_id] = snapshot.processed_frames

        previous_published_frames = self._last_tracking_published_frames.get(camera_id, 0)
        published_delta = max(snapshot.published_frames - previous_published_frames, 0)
        self._metrics.increment_tracking_published_frames(camera_id, published_delta)
        self._last_tracking_published_frames[camera_id] = snapshot.published_frames


def _age_seconds(timestamp: datetime | None) -> float:
    """Return the age of a timestamp in seconds for Prometheus gauges."""

    if timestamp is None:
        return 0.0
    now = datetime.now(timezone.utc)
    return max((now - timestamp).total_seconds(), 0.0)
