"""Lifecycle management for annotated tracking streams."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from src.core.logger.logger import get_logger
from src.services.realtime_video.contracts import (
    MediaMtxStreamEndpoints,
    TrackingTrackSnapshot,
    TrackingWorkerConfig,
    TrackingWorkerMetrics,
)
from src.services.realtime_video.mediamtx import (
    build_stream_endpoints,
    build_tracking_stream_name,
)
from src.services.tracking.detectors.yolo26_detector import Yolo26PersonDetector
from src.services.tracking.identity.milvus_store import MilvusIdentityStore
from src.services.tracking.updates import (
    NullTrackingUpdatePublisher,
    TrackingUpdatePublisher,
)
from src.services.tracking.worker import RealtimeTrackingWorker

TrackingWorkerFactory = Callable[
    [
        TrackingWorkerConfig,
        Yolo26PersonDetector,
        MilvusIdentityStore,
        TrackingUpdatePublisher | None,
        Path | None,
    ],
    RealtimeTrackingWorker,
]


@dataclass(slots=True)
class TrackingSnapshot:
    """Frontend-safe runtime state for one tracking worker."""

    enabled: bool
    stream_name: str
    is_registered: bool
    is_process_alive: bool
    reconnect_attempts: int
    active_tracks: int
    last_error: str | None = None
    tracks: list[TrackingTrackSnapshot] = field(default_factory=list)


class TrackingStreamManager:
    """Manage one annotated tracking worker per camera."""

    def __init__(
        self,
        *,
        detector: Yolo26PersonDetector,
        identity_store: MilvusIdentityStore,
        worker_factory: TrackingWorkerFactory | None = None,
        ffmpeg_binary: str,
        rtsp_base_url: str = "rtsp://localhost:8554",
        hls_base_url: str = "http://localhost:8888",
        whep_base_url: str = "http://localhost:8889",
        sample_fps: float = 5.0,
        output_fps: float = 5.0,
        max_reconnect_attempts: int = 8,
        tracking_suffix: str = "tracked",
        embedder_name: str = "mobilenet",
        embedder_weights_path: Path | None = None,
        tracker_lost_track_buffer: int = 30,
        tracker_activation_threshold: float = 0.7,
        tracker_minimum_consecutive_frames: int = 2,
        tracker_minimum_iou_threshold: float = 0.1,
        tracker_high_conf_det_threshold: float = 0.6,
        identity_sync_interval_seconds: float = 1.0,
        publish_update_interval_seconds: float = 0.5,
        update_publisher: TrackingUpdatePublisher | None = None,
    ) -> None:
        self._detector = detector
        self._identity_store = identity_store
        self._worker_factory = worker_factory or RealtimeTrackingWorker
        self._ffmpeg_binary = ffmpeg_binary
        self._rtsp_base_url = rtsp_base_url
        self._hls_base_url = hls_base_url
        self._whep_base_url = whep_base_url
        self._sample_fps = sample_fps
        self._output_fps = output_fps
        self._max_reconnect_attempts = max_reconnect_attempts
        self._tracking_suffix = tracking_suffix
        self._embedder_name = embedder_name
        self._embedder_weights_path = embedder_weights_path
        self._tracker_lost_track_buffer = tracker_lost_track_buffer
        self._tracker_activation_threshold = tracker_activation_threshold
        self._tracker_minimum_consecutive_frames = tracker_minimum_consecutive_frames
        self._tracker_minimum_iou_threshold = tracker_minimum_iou_threshold
        self._tracker_high_conf_det_threshold = tracker_high_conf_det_threshold
        self._identity_sync_interval_seconds = identity_sync_interval_seconds
        self._publish_update_interval_seconds = publish_update_interval_seconds
        self._update_publisher = update_publisher or NullTrackingUpdatePublisher()
        self._logger = get_logger(__name__)
        self._workers: dict[str, RealtimeTrackingWorker] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start_stream(self, camera_id: str, source_stream_name: str) -> None:
        """Start tracking for a camera if it is not already active."""

        if camera_id in self._tasks and not self._tasks[camera_id].done():
            self._logger.info("Tracking stream for %s is already running.", camera_id)
            return

        annotated_stream_name = build_tracking_stream_name(
            source_stream_name,
            suffix=self._tracking_suffix,
        )
        source_endpoints = build_stream_endpoints(
            source_stream_name,
            rtsp_base_url=self._rtsp_base_url,
            hls_base_url=self._hls_base_url,
            whep_base_url=self._whep_base_url,
        )
        annotated_endpoints = self.stream_endpoints(source_stream_name)
        worker = self._worker_factory(
            TrackingWorkerConfig(
                camera_id=camera_id,
                source_stream_name=source_stream_name,
                annotated_stream_name=annotated_stream_name,
                source_rtsp_url=source_endpoints.rtsp_pull_url,
                annotated_publish_rtsp_url=annotated_endpoints.rtsp_pull_url,
                ffmpeg_binary=self._ffmpeg_binary,
                sample_fps=self._sample_fps,
                output_fps=self._output_fps,
                embedder_name=self._embedder_name,
                tracker_lost_track_buffer=self._tracker_lost_track_buffer,
                tracker_activation_threshold=self._tracker_activation_threshold,
                tracker_minimum_consecutive_frames=self._tracker_minimum_consecutive_frames,
                tracker_minimum_iou_threshold=self._tracker_minimum_iou_threshold,
                tracker_high_conf_det_threshold=self._tracker_high_conf_det_threshold,
                identity_sync_interval_seconds=self._identity_sync_interval_seconds,
                publish_update_interval_seconds=self._publish_update_interval_seconds,
                max_reconnect_attempts=self._max_reconnect_attempts,
            ),
            self._detector,
            self._identity_store,
            self._update_publisher,
            self._embedder_weights_path,
        )
        self._workers[camera_id] = worker
        self._tasks[camera_id] = asyncio.create_task(worker.run())
        self._logger.info("Started tracking worker for %s.", camera_id)

    async def stop_stream(self, camera_id: str) -> None:
        """Stop a running tracking worker."""

        worker = self._workers.pop(camera_id, None)
        task = self._tasks.pop(camera_id, None)
        if worker is None or task is None:
            return
        await worker.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self._logger.info("Stopped tracking worker for %s.", camera_id)

    async def stop_all(self) -> None:
        """Stop all tracking workers."""

        for camera_id in list(self._tasks.keys()):
            await self.stop_stream(camera_id)

    async def close(self) -> None:
        """Release resources owned by the manager."""

        await self.stop_all()
        self._identity_store.close()

    def stream_endpoints(self, source_stream_name: str) -> MediaMtxStreamEndpoints:
        """Return the annotated MediaMTX endpoints for a source stream."""

        return build_stream_endpoints(
            build_tracking_stream_name(source_stream_name, suffix=self._tracking_suffix),
            rtsp_base_url=self._rtsp_base_url,
            hls_base_url=self._hls_base_url,
            whep_base_url=self._whep_base_url,
        )

    def get_snapshot(self, camera_id: str, source_stream_name: str) -> TrackingSnapshot:
        """Return the current tracking state for a camera."""

        worker = self._workers.get(camera_id)
        task = self._tasks.get(camera_id)
        annotated_stream_name = self.stream_endpoints(source_stream_name).stream_name
        if worker is None or task is None:
            return TrackingSnapshot(
                enabled=False,
                stream_name=annotated_stream_name,
                is_registered=False,
                is_process_alive=False,
                reconnect_attempts=0,
                active_tracks=0,
            )

        metrics = _safe_metrics(worker)
        return TrackingSnapshot(
            enabled=True,
            stream_name=annotated_stream_name,
            is_registered=True,
            is_process_alive=not task.done(),
            reconnect_attempts=metrics.reconnect_attempts,
            active_tracks=metrics.active_tracks,
            last_error=metrics.last_error,
            tracks=list(metrics.tracks),
        )


def _safe_metrics(worker: RealtimeTrackingWorker) -> TrackingWorkerMetrics:
    return worker.metrics()
