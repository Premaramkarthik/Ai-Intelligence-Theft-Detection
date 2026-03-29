"""PyAV-based frame extraction workers that pull streams from MediaMTX."""

from __future__ import annotations

import asyncio
import importlib
import threading
from dataclasses import replace
from time import monotonic_ns
from typing import Any

from src.core.logger.logger import get_logger
from src.observability.metrics import MetricsRecorder, NullMetricsRecorder
from src.services.realtime_video.connection_alerts import (
    NullStreamConnectionAlertPublisher,
    StreamConnectionAlertPublisher,
)
from src.services.realtime_video.contracts import (
    FrameSample,
    StreamWorkerConfig,
    StreamWorkerMetrics,
)
from src.services.realtime_video.kafka_bridge import (
    FrameEventPublisher,
    NullFrameEventPublisher,
)
from src.services.realtime_video.queue import FrameQueue


class FrameSamplingGate:
    """Sample decoded frames at a fixed maximum rate."""

    def __init__(self, sample_fps: float) -> None:
        """Create a gate that emits at most the requested FPS."""

        normalized_fps = max(0.1, sample_fps)
        self._sample_interval_ns = int(1_000_000_000 / normalized_fps)
        self._last_emitted_at_ns: int | None = None

    def should_emit(self) -> bool:
        """Return whether a decoded frame should be emitted downstream."""

        candidate_ns = monotonic_ns()
        if (
            self._last_emitted_at_ns is None
            or candidate_ns - self._last_emitted_at_ns >= self._sample_interval_ns
        ):
            self._last_emitted_at_ns = candidate_ns
            return True
        return False


class StreamDeadError(RuntimeError):
    """Raise when a stream has exceeded the maximum reconnect budget."""

    def __init__(self, camera_id: str, attempt_count: int) -> None:
        """Create a terminal stream failure for a repeatedly failing camera."""

        super().__init__(
            f"Realtime frame worker for '{camera_id}' exceeded {attempt_count} reconnect attempts.",
        )


class PyAvFrameWorker:
    """Decode frames from MediaMTX RTSP and sample them for downstream consumers."""

    def __init__(
        self,
        config: StreamWorkerConfig,
        frame_queue: FrameQueue,
        event_publisher: FrameEventPublisher | None = None,
        metrics_recorder: MetricsRecorder | None = None,
        connection_alert_publisher: StreamConnectionAlertPublisher | None = None,
    ) -> None:
        """Create a worker for a single logical stream."""

        self._config = config
        self._frame_queue = frame_queue
        self._event_publisher = event_publisher or NullFrameEventPublisher()
        self._metrics_recorder = metrics_recorder or NullMetricsRecorder()
        self._connection_alert_publisher = (
            connection_alert_publisher or NullStreamConnectionAlertPublisher()
        )
        self._logger = get_logger(__name__)
        self._stop_event = threading.Event()
        self._metrics = StreamWorkerMetrics()
        self._metrics_lock = threading.Lock()
        self._sequence_number = 0
        self._sampling_gate = FrameSamplingGate(config.sample_fps)
        self._last_sample_monotonic_ns: int | None = None
        self._session_connection_alert_sent = False

    async def run(self) -> None:
        """Run the worker until it is stopped, reconnecting with exponential backoff."""

        loop = asyncio.get_running_loop()
        attempt = 0
        try:
            while not self._stop_event.is_set():
                try:
                    await asyncio.to_thread(self._decode_session, loop)
                    attempt = 0
                except Exception as exc:  # pylint: disable=broad-except
                    if self._stop_event.is_set():
                        return
                    attempt += 1
                    self._record_reconnect_failure(exc, attempt)
                    if attempt >= self._config.max_reconnect_attempts:
                        raise StreamDeadError(self._config.camera_id, attempt) from exc
                    delay = _calculate_backoff_seconds(attempt)
                    self._logger.warning(
                        "Realtime frame worker for %s failed: %s. Retrying in %.2fs.",
                        self._config.camera_id,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
        except StreamDeadError as exc:
            self._record_last_error(str(exc))
            self._logger.error("%s", exc)

    async def stop(self) -> None:
        """Stop the worker and break any active decode loop."""

        self._stop_event.set()

    def metrics(self) -> StreamWorkerMetrics:
        """Return a copy of the current worker metrics."""

        with self._metrics_lock:
            return replace(self._metrics)

    def _decode_session(self, loop: asyncio.AbstractEventLoop) -> None:
        """Run one blocking PyAV decode session inside a background thread."""

        av_module = _import_av()
        self._session_connection_alert_sent = False
        container = self._open_container(av_module)
        try:
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"
            stream.codec_context.skip_frame = "NONKEY"
            for packet in container.demux(stream):
                if self._stop_event.is_set():
                    return
                decode_started_ns = monotonic_ns()
                decoded_frames = packet.decode()
                decode_elapsed_ms = (monotonic_ns() - decode_started_ns) / 1_000_000
                per_frame_decode_ms = decode_elapsed_ms / max(1, len(decoded_frames))
                for frame in decoded_frames:
                    if self._stop_event.is_set():
                        return
                    self._record_decoded_frame(per_frame_decode_ms)
                    timestamp_seconds = getattr(frame, "time", None)
                    if not self._sampling_gate.should_emit():
                        continue
                    self._sequence_number += 1
                    sample = FrameSample(
                        camera_id=self._config.camera_id,
                        stream_name=self._config.stream_name,
                        sequence_number=self._sequence_number,
                        source_timestamp_seconds=timestamp_seconds,
                        width=getattr(frame, "width", None),
                        height=getattr(frame, "height", None),
                        pixel_format=str(getattr(frame, "format", "")) or None,
                        frame_array=frame.to_ndarray(format="bgr24"),
                    )
                    self._record_sampled_frame(sample.sampled_monotonic_ns)
                    loop.call_soon_threadsafe(self._publish_sample_to_loop, sample)
        finally:
            container.close()

    def _open_container(self, av_module: Any) -> Any:
        """Open a MediaMTX RTSP stream with low-latency demuxer options."""

        return av_module.open(
            self._config.mediamtx_rtsp_url,
            mode="r",
            timeout=(
                self._config.open_timeout_seconds,
                self._config.read_timeout_seconds,
            ),
            options={
                "rtsp_transport": self._config.rtsp_transport,
                "fflags": "nobuffer",
                "flags": "low_delay",
                "reorder_queue_size": "0",
            },
        )

    def _publish_sample_to_loop(self, sample: FrameSample) -> None:
        """Publish a sampled frame to the async queue without blocking the decode thread."""

        published = self._frame_queue.publish_nowait(sample)
        queue_latency_ms = (monotonic_ns() - sample.sampled_monotonic_ns) / 1_000_000
        if not published:
            self._record_drop(queue_latency_ms)
            return
        self._record_queue_latency(queue_latency_ms)
        self._emit_connection_alert_once()
        asyncio.create_task(self._publish_event_safely(sample))
        self._record_last_frame(sample)

    def _emit_connection_alert_once(self) -> None:
        """Emit a single connection alert for the active decode session."""

        if self._session_connection_alert_sent:
            return
        self._session_connection_alert_sent = True
        self._logger.info(
            "Realtime frame worker for %s connected and is producing frames.",
            self._config.camera_id,
        )
        asyncio.create_task(self._publish_connection_alert_safely())

    async def _publish_event_safely(self, sample: FrameSample) -> None:
        """Publish frame metadata without allowing publisher failures to kill the worker."""

        try:
            await self._event_publisher.publish(sample)
        except Exception as exc:  # pylint: disable=broad-except
            self._record_last_error(str(exc))
            self._logger.warning(
                "Frame event publishing failed for %s: %s",
                self._config.camera_id,
                exc,
            )

    async def _publish_connection_alert_safely(self) -> None:
        """Publish a connection alert without allowing alert failures to kill the worker."""

        try:
            await self._connection_alert_publisher.publish_camera_connected(
                self._config.camera_id,
            )
        except Exception as exc:  # pylint: disable=broad-except
            self._record_last_error(str(exc))
            self._logger.warning(
                "Connection alert publishing failed for %s: %s",
                self._config.camera_id,
                exc,
            )

    def _record_decoded_frame(self, decode_time_ms: float) -> None:
        """Update decoded frame counters from the background decode thread."""

        with self._metrics_lock:
            self._metrics.decoded_frames += 1
            self._metrics.decode_time_ms = decode_time_ms
        self._metrics_recorder.observe_frame_processing_latency(
            self._config.camera_id,
            decode_time_ms,
        )

    def _record_sampled_frame(self, sampled_monotonic_ns: int) -> None:
        """Update sampled frame counters and derive instantaneous sampled FPS."""

        with self._metrics_lock:
            self._metrics.sampled_frames += 1
            if self._last_sample_monotonic_ns is not None:
                delta_ns = sampled_monotonic_ns - self._last_sample_monotonic_ns
                if delta_ns > 0:
                    self._metrics.current_fps = 1_000_000_000 / delta_ns
            self._last_sample_monotonic_ns = sampled_monotonic_ns
        self._metrics_recorder.record_frame_received(self._config.camera_id)

    def _record_drop(self, queue_latency_ms: float) -> None:
        """Record queue drops and the queueing latency observed at drop time."""

        with self._metrics_lock:
            self._metrics.dropped_frames += 1
            self._metrics.queue_latency_ms = queue_latency_ms
        self._metrics_recorder.record_frame_dropped(self._config.camera_id)

    def _record_queue_latency(self, queue_latency_ms: float) -> None:
        """Track the latest measured queue scheduling latency in milliseconds."""

        with self._metrics_lock:
            self._metrics.queue_latency_ms = queue_latency_ms

    def _record_last_frame(self, sample: FrameSample) -> None:
        """Track the timestamps associated with the most recently queued frame."""

        with self._metrics_lock:
            self._metrics.last_frame_at = sample.sampled_at
            self._metrics.last_frame_monotonic_ns = sample.sampled_monotonic_ns

    def _record_reconnect_failure(self, exc: Exception, attempt: int) -> None:
        """Track reconnect attempts and the last failure reason."""

        with self._metrics_lock:
            self._metrics.reconnect_attempts = attempt
            self._metrics.last_error = str(exc)

    def _record_last_error(self, message: str) -> None:
        """Persist the last terminal or non-terminal worker error message."""

        with self._metrics_lock:
            self._metrics.last_error = message


def _import_av() -> Any:
    """Import PyAV lazily to keep the module import-safe when the dependency is absent."""

    return importlib.import_module("av")


def _calculate_backoff_seconds(attempt_number: int) -> float:
    """Calculate reconnect backoff using the same exponential policy across workers."""

    normalized_attempt = max(1, attempt_number)
    return min(15.0, float(2 ** (normalized_attempt - 1)))
