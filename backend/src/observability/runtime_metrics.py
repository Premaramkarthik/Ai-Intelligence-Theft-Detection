"""Periodic runtime metric collection from long-lived backend services."""

# pylint: disable=too-many-instance-attributes

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.observability.metrics import MetricsRecorder
from src.services.tracking_kafka.service import TrackingKafkaProducerService


@dataclass(slots=True)
class RuntimeMetricsDependencies:
    """Runtime dependencies observed by the metrics collector."""

    tracking_kafka_producer: TrackingKafkaProducerService
    stream_manager: object | None = None
    tracking_manager: object | None = None
    kafka_consumer: object | None = None
    mediamtx_service: object | None = None


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
        self._stream_decoded_frames: dict[str, int] = {}
        self._tracking_processed_frames: dict[str, int] = {}
        self._tracking_published_frames: dict[str, int] = {}

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

        self._collect_stream_metrics()
        self._collect_tracking_metrics()
        await self._collect_dependency_health()

    async def _run_loop(self) -> None:
        """Collect runtime metrics until the collector is stopped."""

        while True:
            await self.collect_once()
            await asyncio.sleep(self._interval_seconds)

    def _collect_stream_metrics(self) -> None:
        stream_manager = self._dependencies.stream_manager
        if stream_manager is None:
            return

        active_cameras = list(getattr(stream_manager, "active_cameras")())
        self._metrics.set_stream_worker_count(
            int(getattr(stream_manager, "active_worker_count")())
        )
        for camera_id in active_cameras:
            snapshot = getattr(stream_manager, "get_snapshot")(camera_id)
            self._metrics.set_stream_worker_up(
                camera_id,
                bool(getattr(snapshot, "is_registered", False))
                and bool(getattr(snapshot, "is_process_alive", False)),
            )
            self._metrics.set_stream_reconnect_attempts(
                camera_id,
                int(getattr(snapshot, "reconnect_attempts", 0)),
            )
            self._metrics.set_stream_current_fps(
                camera_id,
                float(getattr(snapshot, "current_fps", 0.0)),
            )
            self._metrics.set_stream_queue_latency_ms(
                camera_id,
                float(getattr(snapshot, "queue_latency_ms", 0.0)),
            )
            self._metrics.set_stream_decode_time_ms(
                camera_id,
                float(getattr(snapshot, "decode_time_ms", 0.0)),
            )
            self._metrics.set_stream_last_frame_age_seconds(
                camera_id,
                _age_seconds(getattr(snapshot, "last_frame_at", None)),
            )
            decoded_frames = int(getattr(snapshot, "decoded_frames", 0))
            previous = self._stream_decoded_frames.get(camera_id, 0)
            self._metrics.increment_stream_decoded_frames(
                camera_id,
                max(decoded_frames - previous, 0),
            )
            self._stream_decoded_frames[camera_id] = decoded_frames

    def _collect_tracking_metrics(self) -> None:
        tracking_manager = self._dependencies.tracking_manager
        if tracking_manager is None:
            return

        active_cameras = list(getattr(tracking_manager, "active_cameras")())
        self._metrics.set_tracking_worker_count(
            int(getattr(tracking_manager, "active_worker_count")())
        )
        for camera_id in active_cameras:
            snapshot = getattr(tracking_manager, "get_runtime_snapshot")(camera_id)
            self._metrics.set_tracking_worker_up(
                camera_id,
                bool(getattr(snapshot, "is_registered", False))
                and bool(getattr(snapshot, "is_process_alive", False)),
            )
            self._metrics.set_tracking_reconnect_attempts(
                camera_id,
                int(getattr(snapshot, "reconnect_attempts", 0)),
            )
            self._metrics.set_tracking_active_tracks(
                camera_id,
                int(getattr(snapshot, "active_tracks", 0)),
            )
            self._metrics.set_tracking_last_frame_age_seconds(
                camera_id,
                _age_seconds(getattr(snapshot, "last_frame_at", None)),
            )
            processed_frames = int(getattr(snapshot, "processed_frames", 0))
            previous_processed = self._tracking_processed_frames.get(camera_id, 0)
            self._metrics.increment_tracking_processed_frames(
                camera_id,
                max(processed_frames - previous_processed, 0),
            )
            self._tracking_processed_frames[camera_id] = processed_frames

            published_frames = int(getattr(snapshot, "published_frames", 0))
            previous_published = self._tracking_published_frames.get(camera_id, 0)
            self._metrics.increment_tracking_published_frames(
                camera_id,
                max(published_frames - previous_published, 0),
            )
            self._tracking_published_frames[camera_id] = published_frames

    async def _collect_dependency_health(self) -> None:
        for component, dependency in (
            ("tracking_kafka_producer", self._dependencies.tracking_kafka_producer),
            ("kafka_consumer", self._dependencies.kafka_consumer),
            ("mediamtx", self._dependencies.mediamtx_service),
        ):
            if dependency is None:
                continue
            snapshot = _coerce_health_snapshot(getattr(dependency, "health_snapshot")())
            self._metrics.set_dependency_health(component, snapshot["healthy"])


def _age_seconds(timestamp: datetime | None) -> float:
    """Return the age of a timestamp in seconds for Prometheus gauges."""

    if timestamp is None:
        return 0.0
    now = datetime.now(timezone.utc)
    return max((now - timestamp).total_seconds(), 0.0)


def _coerce_health_snapshot(snapshot: Any) -> dict[str, bool]:
    if isinstance(snapshot, dict):
        return {"healthy": bool(snapshot.get("healthy", False))}
    return {"healthy": bool(getattr(snapshot, "healthy", False))}
