"""Periodic runtime state collection for backend worker components."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.observability.metrics import NullMetricsRecorder, PrometheusMetrics


@dataclass(slots=True)
class RuntimeMetricsDependencies:
    """Resolved services used by the runtime metrics collector."""

    stream_manager: object | None = None
    tracking_manager: object | None = None
    tracking_kafka_producer: object | None = None
    kafka_consumer: object | None = None
    mediamtx_service: object | None = None
    opencv_pipeline: object | None = None
    webrtc_registry: object | None = None
    inference_manager: object | None = None
    identity_store: object | None = None


class RuntimeMetricsCollector:
    """Poll runtime state snapshots and publish them as Prometheus metrics."""

    def __init__(
        self,
        *,
        metrics: PrometheusMetrics | NullMetricsRecorder,
        dependencies: RuntimeMetricsDependencies,
        interval_seconds: float = 5.0,
    ) -> None:
        self._metrics = metrics
        self._dependencies = dependencies
        self._interval_seconds = max(interval_seconds, 0.5)
        self._task: asyncio.Task[None] | None = None
        self._stream_decoded_totals: dict[str, int] = {}
        self._tracking_processed_totals: dict[str, int] = {}
        self._tracking_published_totals: dict[str, int] = {}

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def collect_once(self) -> None:
        self._collect_stream_manager()
        self._collect_tracking_manager()
        self._collect_pipeline_runtime()
        self._collect_dependency_health()

    async def _run(self) -> None:
        while True:
            await self.collect_once()
            await asyncio.sleep(self._interval_seconds)

    def _collect_stream_manager(self) -> None:
        manager = self._dependencies.stream_manager
        if manager is None:
            return
        active_cameras = list(_call0(manager, "active_cameras") or [])
        self._metrics.set_stream_worker_count(int(_call0(manager, "active_worker_count") or len(active_cameras)))
        for camera_id in active_cameras:
            snapshot = manager.get_snapshot(camera_id)
            is_up = bool(getattr(snapshot, "is_registered", False) and getattr(snapshot, "is_process_alive", False))
            self._metrics.set_stream_worker_up(camera_id, is_up)
            self._metrics.set_stream_reconnect_attempts(
                camera_id,
                int(getattr(snapshot, "reconnect_attempts", 0) or 0),
            )
            self._metrics.set_stream_current_fps(
                camera_id,
                float(getattr(snapshot, "current_fps", 0.0) or 0.0),
            )
            self._metrics.set_stream_queue_latency_ms(
                camera_id,
                float(getattr(snapshot, "queue_latency_ms", 0.0) or 0.0),
            )
            self._metrics.set_stream_decode_time_ms(
                camera_id,
                float(getattr(snapshot, "decode_time_ms", 0.0) or 0.0),
            )
            last_frame_at = getattr(snapshot, "last_frame_at", None)
            if last_frame_at is not None:
                self._metrics.set_stream_last_frame_age_seconds(camera_id, _age_seconds(last_frame_at))
            current_decoded = int(getattr(snapshot, "decoded_frames", 0) or 0)
            previous_decoded = self._stream_decoded_totals.get(camera_id, 0)
            if current_decoded > previous_decoded:
                self._metrics.increment_stream_decoded_frames(camera_id, current_decoded - previous_decoded)
            self._stream_decoded_totals[camera_id] = current_decoded

    def _collect_tracking_manager(self) -> None:
        manager = self._dependencies.tracking_manager
        if manager is None:
            return
        active_cameras = list(_call0(manager, "active_cameras") or [])
        self._metrics.set_tracking_worker_count(
            int(_call0(manager, "active_worker_count") or len(active_cameras))
        )
        for camera_id in active_cameras:
            snapshot = manager.get_runtime_snapshot(camera_id)
            is_up = bool(getattr(snapshot, "is_registered", False) and getattr(snapshot, "is_process_alive", False))
            self._metrics.set_tracking_worker_up(camera_id, is_up)
            self._metrics.set_tracking_active_tracks(
                camera_id,
                int(getattr(snapshot, "active_tracks", 0) or 0),
            )
            last_frame_at = getattr(snapshot, "last_frame_at", None)
            if last_frame_at is not None:
                self._metrics.set_stream_last_frame_age_seconds(camera_id, _age_seconds(last_frame_at))
            processed_frames = int(getattr(snapshot, "processed_frames", 0) or 0)
            previous_processed = self._tracking_processed_totals.get(camera_id, 0)
            if processed_frames > previous_processed:
                self._metrics.increment_tracking_processed_frames(
                    camera_id,
                    processed_frames - previous_processed,
                )
            self._tracking_processed_totals[camera_id] = processed_frames
            published_frames = int(getattr(snapshot, "published_frames", 0) or 0)
            previous_published = self._tracking_published_totals.get(camera_id, 0)
            if published_frames > previous_published:
                self._metrics.increment_tracking_published_frames(
                    camera_id,
                    published_frames - previous_published,
                )
            self._tracking_published_totals[camera_id] = published_frames

    def _collect_pipeline_runtime(self) -> None:
        runtime = self._dependencies.opencv_pipeline
        if runtime is None:
            return
        active_cameras = list(getattr(runtime, "_active_cameras", {}).keys())
        self._metrics.set_active_cameras(len(active_cameras))
        self._metrics.set_stream_worker_count(len(active_cameras))
        self._metrics.set_tracking_worker_count(len(active_cameras))
        last_frame_seen_at = getattr(runtime, "_last_frame_seen_at", {})
        last_active_tracks = getattr(runtime, "_last_active_tracks", {})
        last_queue_latency_ms = getattr(runtime, "_last_queue_latency_ms", {})
        last_decode_time_ms = getattr(runtime, "_last_decode_time_ms", {})
        last_stream_fps = getattr(runtime, "_last_stream_fps", {})
        last_reconnect_attempts = getattr(runtime, "_last_reconnect_attempts", {})
        inference_manager = self._dependencies.inference_manager
        webrtc_registry = self._dependencies.webrtc_registry

        for camera_id, active_camera in getattr(runtime, "_active_cameras", {}).items():
            snapshot = active_camera.worker.health_snapshot()
            self._metrics.set_stream_worker_up(camera_id, bool(snapshot.healthy))
            self._metrics.set_stream_reconnect_attempts(
                camera_id,
                int(getattr(snapshot, "reconnect_attempts", last_reconnect_attempts.get(camera_id, 0)) or 0),
            )
            self._metrics.set_stream_current_fps(
                camera_id,
                float(getattr(snapshot, "current_fps", last_stream_fps.get(camera_id, 0.0)) or 0.0),
            )
            self._metrics.set_stream_decode_time_ms(
                camera_id,
                float(getattr(snapshot, "decode_time_ms", last_decode_time_ms.get(camera_id, 0.0)) or 0.0),
            )
            self._metrics.set_stream_queue_latency_ms(
                camera_id,
                float(last_queue_latency_ms.get(camera_id, 0.0) or 0.0),
            )
            if camera_id in last_frame_seen_at:
                self._metrics.set_stream_last_frame_age_seconds(
                    camera_id,
                    _age_seconds(last_frame_seen_at[camera_id]),
                )
            self._metrics.set_tracking_active_tracks(
                camera_id,
                int(last_active_tracks.get(camera_id, 0) or 0),
            )
            if inference_manager is not None:
                inference_snapshot = inference_manager.get_snapshot(camera_id)
                if inference_snapshot is not None:
                    self._metrics.set_inference_queue_depth(
                        camera_id,
                        int(inference_snapshot.queue_depth or 0),
                    )
            if webrtc_registry is not None:
                self._metrics.set_webrtc_viewers(
                    camera_id,
                    int(webrtc_registry.active_track_count(camera_id)),
                )

    def _collect_dependency_health(self) -> None:
        mapping = {
            "tracking_kafka_producer": self._dependencies.tracking_kafka_producer,
            "kafka_consumer": self._dependencies.kafka_consumer,
            "mediamtx": self._dependencies.mediamtx_service,
            "identity_store": self._dependencies.identity_store,
        }
        for component, dependency in mapping.items():
            if dependency is None:
                continue
            healthy = _extract_healthy(dependency)
            if healthy is not None:
                self._metrics.set_dependency_health(component, healthy)


def _call0(target: object, method_name: str):
    method = getattr(target, method_name, None)
    if not callable(method):
        return None
    return method()


def _age_seconds(timestamp: datetime) -> float:
    now = datetime.now(timezone.utc)
    reference = timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=timezone.utc)
    return max((now - reference).total_seconds(), 0.0)


def _extract_healthy(dependency: object) -> bool | None:
    health_snapshot = getattr(dependency, "health_snapshot", None)
    if callable(health_snapshot):
        snapshot = health_snapshot()
        if isinstance(snapshot, dict):
            healthy = snapshot.get("healthy")
            if isinstance(healthy, bool):
                return healthy
        healthy = getattr(snapshot, "healthy", None)
        if isinstance(healthy, bool):
            return healthy
    healthy = getattr(dependency, "healthy", None)
    if isinstance(healthy, bool):
        return healthy
    return None
