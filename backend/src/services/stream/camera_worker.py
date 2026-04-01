from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiokafka import AIOKafkaProducer

from src.core.logger.logger import configure_logging
from src.models.camera import StreamDesiredState, StreamProtocol, StreamStatus
from src.schemas.stream_responses import StreamEventPayload
from src.utils.ffmpeg import build_ffmpeg_hls_command
from src.utils.retry import sleep_with_retry_logging


@dataclass(slots=True)
class WorkerRuntimeConfig:
    camera_id: str
    camera_name: str
    stream_id: str
    rtsp_url: str
    transport: str
    ffmpeg_binary: str
    kafka_bootstrap_servers: str
    kafka_enabled: bool
    topic_camera_status: str
    topic_camera_events: str
    topic_camera_ai_results: str
    playback_path: str
    playlist_path: str
    segment_time_seconds: int
    playlist_size: int
    worker_start_timeout_seconds: int
    heartbeat_interval_seconds: int
    reconnect_base_delay_seconds: float
    reconnect_max_delay_seconds: float
    log_level: str = "INFO"
    json_logs: bool = False
    restart_count: int = 0


@dataclass(slots=True)
class WorkerState:
    reconnect_attempts: int = 0
    stderr_tail: deque[str] = field(default_factory=lambda: deque(maxlen=30))


def run_camera_worker_process(config: WorkerRuntimeConfig, stop_event: Any) -> None:
    configure_logging(config.log_level, config.json_logs)
    asyncio.run(_run_worker(config, stop_event))


async def _run_worker(config: WorkerRuntimeConfig, stop_event: Any) -> None:
    logger = logging.getLogger(__name__)
    producer: AIOKafkaProducer | None = None
    state = WorkerState()

    try:
        if config.kafka_enabled:
            producer = AIOKafkaProducer(
                bootstrap_servers=config.kafka_bootstrap_servers,
                value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            )
            await producer.start()

        while not stop_event.is_set():
            state.stderr_tail.clear()
            playlist_path = Path(config.playlist_path)
            playlist_path.parent.mkdir(parents=True, exist_ok=True)
            process = await asyncio.create_subprocess_exec(
                *build_ffmpeg_hls_command(
                    ffmpeg_binary=config.ffmpeg_binary,
                    rtsp_url=config.rtsp_url,
                    transport=config.transport,
                    playlist_path=playlist_path,
                    segment_time_seconds=config.segment_time_seconds,
                    playlist_size=config.playlist_size,
                ),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            stderr_task = asyncio.create_task(_consume_stderr(process, state.stderr_tail, logger))
            await _publish_status_event(
                producer,
                config,
                status=StreamStatus.starting,
                event="stream_starting",
                message="Worker process started FFmpeg for RTSP ingestion.",
                process_id=process.pid,
                reconnect_attempts=state.reconnect_attempts,
            )

            ready = await _wait_for_playlist(
                playlist_path,
                process,
                config.worker_start_timeout_seconds,
                stop_event,
            )
            if not ready:
                await _terminate_process(process)
                await stderr_task
                await _publish_status_event(
                    producer,
                    config,
                    status=StreamStatus.error,
                    event="stream_start_failed",
                    message="FFmpeg did not produce an HLS playlist in time.",
                    process_id=process.pid,
                    reconnect_attempts=state.reconnect_attempts,
                    error_code="PLAYLIST_TIMEOUT",
                    error_message="\n".join(state.stderr_tail) or None,
                )
                if stop_event.is_set():
                    break
                state.reconnect_attempts += 1
                await _publish_status_event(
                    producer,
                    config,
                    status=StreamStatus.reconnecting,
                    event="reconnect_scheduled",
                    message="Worker is retrying the RTSP connection after startup failure.",
                    reconnect_attempts=state.reconnect_attempts,
                )
                await sleep_with_retry_logging(
                    logger,
                    operation_name=f"camera_worker_startup_retry[{config.camera_id}]",
                    attempt=state.reconnect_attempts,
                    base_delay=config.reconnect_base_delay_seconds,
                    max_delay=config.reconnect_max_delay_seconds,
                    reason="FFmpeg did not produce an HLS playlist in time.",
                )
                continue

            await _publish_status_event(
                producer,
                config,
                status=StreamStatus.running,
                event="stream_started",
                message="Stream is running and HLS playlist is available.",
                process_id=process.pid,
                reconnect_attempts=state.reconnect_attempts,
            )
            state.reconnect_attempts = 0

            while not stop_event.is_set():
                if process.returncode is not None:
                    break
                await asyncio.sleep(config.heartbeat_interval_seconds)
                if process.returncode is not None:
                    break
                await _publish_status_event(
                    producer,
                    config,
                    status=StreamStatus.running,
                    event="stream_heartbeat",
                    message="Worker heartbeat.",
                    process_id=process.pid,
                    reconnect_attempts=state.reconnect_attempts,
                )

            if stop_event.is_set():
                await _terminate_process(process)
                await stderr_task
                await _publish_status_event(
                    producer,
                    config,
                    status=StreamStatus.stopped,
                    event="stream_stopped",
                    message="Stream stopped by control request.",
                    process_id=process.pid,
                )
                await _publish_lifecycle_event(
                    producer,
                    config.topic_camera_events,
                    config,
                    status=StreamStatus.stopped,
                    event="stream_stopped",
                    message="Stream stopped by control request.",
                    process_id=process.pid,
                )
                break

            await stderr_task
            await _publish_status_event(
                producer,
                config,
                status=StreamStatus.error,
                event="stream_error",
                message="FFmpeg exited unexpectedly and the worker will reconnect.",
                process_id=process.pid,
                reconnect_attempts=state.reconnect_attempts,
                error_code="FFMPEG_EXIT",
                error_message="\n".join(state.stderr_tail) or None,
            )
            state.reconnect_attempts += 1
            await _publish_status_event(
                producer,
                config,
                status=StreamStatus.reconnecting,
                event="reconnect_attempt",
                message="Worker is reconnecting to the RTSP source.",
                reconnect_attempts=state.reconnect_attempts,
            )
            await sleep_with_retry_logging(
                logger,
                operation_name=f"camera_worker_reconnect[{config.camera_id}]",
                attempt=state.reconnect_attempts,
                base_delay=config.reconnect_base_delay_seconds,
                max_delay=config.reconnect_max_delay_seconds,
                reason="FFmpeg exited unexpectedly and the worker will reconnect.",
            )

    finally:
        if producer is not None:
            await producer.stop()


async def _publish_status_event(
    producer: AIOKafkaProducer | None,
    config: WorkerRuntimeConfig,
    *,
    status: StreamStatus,
    event: str,
    message: str,
    process_id: int | None = None,
    reconnect_attempts: int = 0,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    payload = StreamEventPayload(
        camera_id=config.camera_id,
        camera_name=config.camera_name,
        stream_id=config.stream_id,
        event=event,
        status=status,
        protocol=StreamProtocol.hls,
        message=message,
        playback_url=config.playback_path,
        playlist_path=config.playlist_path,
        process_id=process_id,
        desired_state=(
            StreamDesiredState.stopped
            if status in {StreamStatus.stopped, StreamStatus.stopping}
            else StreamDesiredState.running
        ),
        reconnect_attempts=reconnect_attempts,
        restart_count=config.restart_count,
        error_code=error_code,
        error_message=error_message,
    )
    await _publish_payload(producer, config.topic_camera_status, payload)
    if event != "stream_heartbeat":
        await _publish_lifecycle_event(
            producer,
            config.topic_camera_events,
            config,
            status=status,
            event=event,
            message=message,
            process_id=process_id,
            reconnect_attempts=reconnect_attempts,
            error_code=error_code,
            error_message=error_message,
        )


async def _publish_lifecycle_event(
    producer: AIOKafkaProducer | None,
    topic: str,
    config: WorkerRuntimeConfig,
    *,
    status: StreamStatus,
    event: str,
    message: str,
    process_id: int | None = None,
    reconnect_attempts: int = 0,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    payload = StreamEventPayload(
        camera_id=config.camera_id,
        camera_name=config.camera_name,
        stream_id=config.stream_id,
        event=event,
        status=status,
        protocol=StreamProtocol.hls,
        message=message,
        playback_url=config.playback_path,
        playlist_path=config.playlist_path,
        process_id=process_id,
        desired_state=(
            StreamDesiredState.stopped
            if status in {StreamStatus.stopped, StreamStatus.stopping}
            else StreamDesiredState.running
        ),
        reconnect_attempts=reconnect_attempts,
        restart_count=config.restart_count,
        error_code=error_code,
        error_message=error_message,
    )
    await _publish_payload(producer, topic, payload)


async def _publish_payload(
    producer: AIOKafkaProducer | None,
    topic: str,
    payload: StreamEventPayload,
) -> None:
    if producer is None:
        return
    await producer.send_and_wait(topic, payload.model_dump(mode="json"))


async def _wait_for_playlist(
    playlist_path: Path,
    process: asyncio.subprocess.Process,
    timeout_seconds: int,
    stop_event: Any,
) -> bool:
    remaining = timeout_seconds
    while remaining > 0:
        if stop_event.is_set():
            return False
        if process.returncode is not None:
            return False
        if await asyncio.to_thread(_playlist_available, playlist_path):
            return True
        await asyncio.sleep(1)
        remaining -= 1
    return False


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(process.wait(), timeout=5)
    if process.returncode is None:
        process.kill()
        await process.wait()


async def _consume_stderr(
    process: asyncio.subprocess.Process,
    stderr_tail: deque[str],
    logger: logging.Logger,
) -> None:
    if process.stderr is None:
        return
    while True:
        line = await process.stderr.readline()
        if not line:
            break
        decoded = line.decode("utf-8", errors="ignore").strip()
        if decoded:
            stderr_tail.append(decoded)
            logger.warning("FFmpeg stderr: %s", decoded)


def _playlist_available(playlist_path: Path) -> bool:
    return playlist_path.exists() and playlist_path.stat().st_size > 0
