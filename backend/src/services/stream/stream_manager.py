from __future__ import annotations

import asyncio
import contextlib
import multiprocessing
from dataclasses import dataclass
from datetime import datetime, timezone
from multiprocessing.process import BaseProcess
from pathlib import Path

from src.core.config import Settings
from src.core.exceptions.stream.stream_exceptions import (
    StreamAlreadyRunningException,
    StreamNotRunningException,
    StreamWorkerStartException,
)
from src.core.logger.logger import get_logger
from src.models.camera import CameraRecord, StreamDesiredState
from src.schemas.stream_requests import StreamStartRequest
from src.services.stream.camera_worker import WorkerRuntimeConfig, run_camera_worker_process


@dataclass(slots=True)
class WorkerSnapshot:
    desired_state: StreamDesiredState
    is_registered: bool
    is_process_alive: bool
    process_id: int | None
    restart_count: int
    reconnect_attempts: int


@dataclass(slots=True)
class WorkerHandle:
    camera_id: str
    worker_config: WorkerRuntimeConfig
    process: BaseProcess
    stop_event: object
    desired_state: StreamDesiredState
    registered_at: datetime
    restart_count: int = 0
    reconnect_attempts: int = 0


class StreamManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger(__name__)
        self._context = multiprocessing.get_context("spawn")
        self._registry: dict[str, WorkerHandle] = {}
        self._lock = asyncio.Lock()
        self._monitor_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor_task
        camera_ids = list(self._registry.keys())
        for camera_id in camera_ids:
            with contextlib.suppress(StreamNotRunningException):
                await self.stop_worker(camera_id)

    async def start_worker(
        self,
        camera: CameraRecord,
        rtsp_url: str,
        request: StreamStartRequest,
        playback_path: str,
        playlist_path: str,
    ) -> WorkerSnapshot:
        async with self._lock:
            existing = self._registry.get(camera.id)
            if existing and existing.process.is_alive():
                if not request.force_restart:
                    raise StreamAlreadyRunningException(camera.id)
                await self._stop_handle(existing)

            self._cleanup_output_dir(Path(playlist_path).parent)
            worker_config = WorkerRuntimeConfig(
                camera_id=camera.id,
                camera_name=camera.name,
                stream_id=f"stream_{camera.id}",
                rtsp_url=rtsp_url,
                transport=camera.transport.value,
                ffmpeg_binary=self._settings.ffmpeg_binary,
                kafka_bootstrap_servers=self._settings.kafka_bootstrap_servers,
                kafka_enabled=self._settings.kafka_enabled,
                topic_camera_status=self._settings.kafka_topic_camera_status,
                topic_camera_events=self._settings.kafka_topic_camera_events,
                topic_camera_ai_results=self._settings.kafka_topic_camera_ai_results,
                playback_path=playback_path,
                playlist_path=playlist_path,
                segment_time_seconds=self._settings.hls_segment_time_seconds,
                playlist_size=self._settings.hls_playlist_size,
                worker_start_timeout_seconds=self._settings.stream_start_timeout_seconds,
                heartbeat_interval_seconds=self._settings.worker_heartbeat_interval_seconds,
                reconnect_base_delay_seconds=self._settings.reconnect_base_delay_seconds,
                reconnect_max_delay_seconds=self._settings.reconnect_max_delay_seconds,
                log_level=self._settings.log_level,
                json_logs=self._settings.json_logs,
                file_logs_enabled=self._settings.file_logs_enabled,
                log_directory=self._settings.log_directory,
                log_file_prefix=self._settings.log_file_prefix,
                log_file_max_bytes=self._settings.log_file_max_bytes,
                log_file_backup_count=self._settings.log_file_backup_count,
            )
            stop_event = self._context.Event()
            process = self._context.Process(
                target=run_camera_worker_process,
                args=(worker_config, stop_event),
                name=f"camera-worker-{camera.id}",
                daemon=True,
            )
            process.start()
            if process.pid is None:
                raise StreamWorkerStartException(camera.id)

            self._registry[camera.id] = WorkerHandle(
                camera_id=camera.id,
                worker_config=worker_config,
                process=process,
                stop_event=stop_event,
                desired_state=StreamDesiredState.running,
                registered_at=datetime.now(timezone.utc),
            )
            return self.get_snapshot(camera.id)

    async def stop_worker(self, camera_id: str) -> WorkerSnapshot:
        async with self._lock:
            handle = self._registry.get(camera_id)
            if handle is None or not handle.process.is_alive():
                self._registry.pop(camera_id, None)
                raise StreamNotRunningException(camera_id)
            await self._stop_handle(handle)
            self._registry.pop(camera_id, None)
            return WorkerSnapshot(
                desired_state=StreamDesiredState.stopped,
                is_registered=False,
                is_process_alive=False,
                process_id=None,
                restart_count=handle.restart_count,
                reconnect_attempts=handle.reconnect_attempts,
            )

    def get_snapshot(self, camera_id: str) -> WorkerSnapshot:
        handle = self._registry.get(camera_id)
        if handle is None:
            return WorkerSnapshot(
                desired_state=StreamDesiredState.stopped,
                is_registered=False,
                is_process_alive=False,
                process_id=None,
                restart_count=0,
                reconnect_attempts=0,
            )
        return WorkerSnapshot(
            desired_state=handle.desired_state,
            is_registered=True,
            is_process_alive=handle.process.is_alive(),
            process_id=handle.process.pid,
            restart_count=handle.restart_count,
            reconnect_attempts=handle.reconnect_attempts,
        )

    def note_event(self, camera_id: str, reconnect_attempts: int, restart_count: int) -> None:
        handle = self._registry.get(camera_id)
        if handle is None:
            return
        handle.reconnect_attempts = reconnect_attempts
        handle.restart_count = max(handle.restart_count, restart_count)

    def active_worker_count(self) -> int:
        return sum(1 for handle in self._registry.values() if handle.process.is_alive())

    async def _stop_handle(self, handle: WorkerHandle) -> None:
        handle.desired_state = StreamDesiredState.stopped
        handle.stop_event.set()
        await asyncio.to_thread(handle.process.join, self._settings.worker_shutdown_grace_seconds)
        if handle.process.is_alive():
            handle.process.terminate()
            await asyncio.to_thread(handle.process.join, 5)

    async def _monitor_loop(self) -> None:
        while True:
            await asyncio.sleep(self._settings.worker_monitor_interval_seconds)
            async with self._lock:
                for camera_id, handle in list(self._registry.items()):
                    if handle.desired_state != StreamDesiredState.running:
                        continue
                    if handle.process.is_alive():
                        continue
                    handle.restart_count += 1
                    handle.worker_config.restart_count = handle.restart_count
                    self._logger.warning(
                        "Worker for camera %s exited unexpectedly. Restarting process.",
                        camera_id,
                    )
                    stop_event = self._context.Event()
                    process = self._context.Process(
                        target=run_camera_worker_process,
                        args=(handle.worker_config, stop_event),
                        name=f"camera-worker-{camera_id}",
                        daemon=True,
                    )
                    process.start()
                    if process.pid is None:
                        self._logger.error("Worker restart failed for camera %s", camera_id)
                        continue
                    handle.process = process
                    handle.stop_event = stop_event

    def _cleanup_output_dir(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for entry in output_dir.iterdir():
            if entry.is_file():
                entry.unlink()
