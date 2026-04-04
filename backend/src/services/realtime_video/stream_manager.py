"""Async orchestration for many PyAV frame workers in one Python process."""

# pylint: disable=duplicate-code,too-many-instance-attributes,too-many-arguments

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from src.core.logger.logger import get_logger
from src.models.camera import StreamDesiredState
from src.observability.metrics import MetricsRecorder, NullMetricsRecorder
from src.services.realtime_video.connection_alerts import (
    NullStreamConnectionAlertPublisher,
    StreamConnectionAlertPublisher,
)
from src.services.realtime_video.contracts import (
    MediaMtxStreamEndpoints,
    StreamWorkerConfig,
    StreamWorkerMetrics,
)
from src.services.realtime_video.frame_worker import PyAvFrameWorker
from src.services.realtime_video.kafka_bridge import FrameEventPublisher
from src.services.realtime_video.mediamtx import build_stream_endpoints
from src.services.realtime_video.queue import FrameQueue

WorkerFactory = Callable[
    [
        StreamWorkerConfig,
        FrameQueue,
        FrameEventPublisher | None,
        MetricsRecorder,
        StreamConnectionAlertPublisher | None,
    ],
    PyAvFrameWorker,
]


@dataclass(slots=True)
class WorkerSnapshot:
    """Expose the frontend-facing runtime state for a realtime frame worker."""

    desired_state: StreamDesiredState
    is_registered: bool
    is_process_alive: bool
    process_id: int | None
    restart_count: int
    reconnect_attempts: int
    decoded_frames: int = 0
    sampled_frames: int = 0
    dropped_frames: int = 0
    current_fps: float = 0.0
    queue_latency_ms: float = 0.0
    decode_time_ms: float = 0.0
    last_frame_at: datetime | None = None


class MediaMtxStreamManager:  # pylint: disable=too-many-instance-attributes
    """Manage multiple PyAV stream workers inside a single asyncio event loop."""

    def __init__(
        self,
        frame_queue: FrameQueue,
        *,
        event_publisher: FrameEventPublisher | None = None,
        worker_factory: WorkerFactory | None = None,
        rtsp_base_url: str = "rtsp://localhost:8554",
        hls_base_url: str = "http://localhost:8888",
        whep_base_url: str = "http://localhost:8889",
        max_reconnect_attempts: int = 8,
        metrics_recorder: MetricsRecorder | None = None,
        connection_alert_publisher: StreamConnectionAlertPublisher | None = None,
    ) -> None:  # pylint: disable=too-many-arguments
        """Create a stream manager with a shared queue and worker factory."""

        self._frame_queue = frame_queue
        self._event_publisher = event_publisher
        self._worker_factory = worker_factory or PyAvFrameWorker
        self._metrics_recorder = metrics_recorder or NullMetricsRecorder()
        self._connection_alert_publisher = (
            connection_alert_publisher or NullStreamConnectionAlertPublisher()
        )
        self._rtsp_base_url = rtsp_base_url
        self._hls_base_url = hls_base_url
        self._whep_base_url = whep_base_url
        self._max_reconnect_attempts = max_reconnect_attempts
        self._logger = get_logger(__name__)
        self._workers: dict[str, PyAvFrameWorker] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start_stream(
        self,
        camera_id: str,
        stream_name: str,
        sample_fps: float = 5.0,
    ) -> None:
        """Start frame extraction for a MediaMTX path if it is not already running."""

        if camera_id in self._tasks and not self._tasks[camera_id].done():
            self._logger.info("Realtime stream for %s is already running.", camera_id)
            return

        endpoints = self.stream_endpoints(stream_name)
        worker = self._worker_factory(
            StreamWorkerConfig(
                camera_id=camera_id,
                stream_name=stream_name,
                mediamtx_rtsp_url=endpoints.rtsp_pull_url,
                sample_fps=sample_fps,
                max_reconnect_attempts=self._max_reconnect_attempts,
            ),
            self._frame_queue,
            self._event_publisher,
            self._metrics_recorder,
            self._connection_alert_publisher,
        )
        self._workers[camera_id] = worker
        task = asyncio.create_task(worker.run(), name=f"frame-worker:{camera_id}")
        task.add_done_callback(
            lambda completed_task, tracked_camera_id=camera_id: self._handle_worker_exit(
                tracked_camera_id,
                completed_task,
            ),
        )
        self._tasks[camera_id] = task
        self._logger.info("Started realtime frame worker for %s.", camera_id)

    async def stop_stream(self, camera_id: str) -> None:
        """Stop a running frame worker and wait for it to exit."""

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
        self._logger.info("Stopped realtime frame worker for %s.", camera_id)

    async def stop_all(self) -> None:
        """Stop all running workers managed by this process."""

        for camera_id in list(self._tasks.keys()):
            await self.stop_stream(camera_id)

    def stream_endpoints(self, stream_name: str) -> MediaMtxStreamEndpoints:
        """Return the MediaMTX endpoints for a logical stream name."""

        return build_stream_endpoints(
            stream_name,
            rtsp_base_url=self._rtsp_base_url,
            hls_base_url=self._hls_base_url,
            whep_base_url=self._whep_base_url,
        )

    def active_cameras(self) -> list[str]:
        """Return camera identifiers that currently have active workers."""

        return sorted(
            camera_id
            for camera_id, task in self._tasks.items()
            if not task.done()
        )

    def get_snapshot(self, camera_id: str) -> WorkerSnapshot:
        """Return a stable runtime snapshot for one managed realtime worker."""

        worker = self._workers.get(camera_id)
        task = self._tasks.get(camera_id)
        if worker is None or task is None:
            return WorkerSnapshot(
                desired_state=StreamDesiredState.stopped,
                is_registered=False,
                is_process_alive=False,
                process_id=None,
                restart_count=0,
                reconnect_attempts=0,
            )

        metrics = _safe_metrics(worker)
        return WorkerSnapshot(
            desired_state=(
                StreamDesiredState.running
                if not task.done()
                else StreamDesiredState.stopped
            ),
            is_registered=True,
            is_process_alive=not task.done(),
            process_id=None,
            restart_count=0,
            reconnect_attempts=metrics.reconnect_attempts,
            decoded_frames=metrics.decoded_frames,
            sampled_frames=metrics.sampled_frames,
            dropped_frames=metrics.dropped_frames,
            current_fps=metrics.current_fps,
            queue_latency_ms=metrics.queue_latency_ms,
            decode_time_ms=metrics.decode_time_ms,
            last_frame_at=metrics.last_frame_at,
        )

    def active_worker_count(self) -> int:
        """Return the number of currently active realtime workers."""

        return len(self.active_cameras())

    def set_connection_alert_publisher(
        self,
        publisher: StreamConnectionAlertPublisher,
    ) -> None:
        """Attach the alert publisher used by newly created realtime workers."""

        self._connection_alert_publisher = publisher

    def _handle_worker_exit(
        self,
        camera_id: str,
        task: asyncio.Task[None],
    ) -> None:
        """Clean up completed workers and publish terminal disconnect alerts when needed."""

        worker = self._workers.pop(camera_id, None)
        self._tasks.pop(camera_id, None)
        if worker is None or task.cancelled():
            return

        try:
            task.result()
        except Exception as exc:  # pylint: disable=broad-except
            self._logger.exception(
                "Realtime frame worker task for %s exited with an unhandled exception: %s",
                camera_id,
                exc,
            )
            return

        metrics = worker.metrics()
        if (
            metrics.reconnect_attempts < self._max_reconnect_attempts
            or not metrics.last_error
        ):
            return

        asyncio.create_task(
            self._connection_alert_publisher.publish_camera_disconnected(
                camera_id,
                reconnect_attempts=metrics.reconnect_attempts,
                error_message=metrics.last_error,
            ),
        )


def _safe_metrics(worker: PyAvFrameWorker) -> StreamWorkerMetrics:
    """Return worker metrics without letting instrumentation failures break APIs."""

    return worker.metrics()
