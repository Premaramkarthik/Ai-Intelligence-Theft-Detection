"""Tracking worker that annotates a second MediaMTX stream with Deep SORT IDs."""

from __future__ import annotations

import asyncio
import importlib
import subprocess
import threading
from dataclasses import replace
from datetime import datetime, timezone
from time import monotonic_ns
from typing import Any

import cv2
import numpy as np

from src.core.logger.logger import get_logger
from src.services.deep_sort_realtime.deepsort_tracker import DeepSort
from src.services.realtime_video.contracts import (
    TrackingTrackSnapshot,
    TrackingWorkerConfig,
    TrackingWorkerMetrics,
)
from src.services.realtime_video.frame_worker import (
    FrameSamplingGate,
    StreamDeadError,
    _calculate_backoff_seconds,
)
from src.services.tracking.detectors.yolo26_detector import Yolo26PersonDetector
from src.services.tracking.identity.milvus_store import MilvusIdentityStore
from src.services.tracking.updates import (
    NullTrackingUpdatePublisher,
    TrackingUpdatePublisher,
)
from src.utils.ffmpeg import build_ffmpeg_rtsp_publish_command


class RealtimeTrackingWorker:
    """Decode, track, annotate, and republish one camera stream."""

    def __init__(
        self,
        config: TrackingWorkerConfig,
        detector: Yolo26PersonDetector,
        identity_store: MilvusIdentityStore,
        update_publisher: TrackingUpdatePublisher | None = None,
        embedder_weights_path: str | None = None,
    ) -> None:
        self._config = config
        self._detector = detector
        self._identity_store = identity_store
        self._update_publisher = update_publisher or NullTrackingUpdatePublisher()
        self._embedder_weights_path = embedder_weights_path
        self._logger = get_logger(__name__)
        self._stop_event = threading.Event()
        self._metrics = TrackingWorkerMetrics()
        self._metrics_lock = threading.Lock()
        self._sampling_gate = FrameSamplingGate(config.sample_fps)
        self._publish_gate = FrameSamplingGate(config.output_fps)
        self._tracker = DeepSort(
            embedder=config.embedder_name,
            embedder_wts=str(embedder_weights_path) if embedder_weights_path else None,
        )
        self._publisher: _AnnotatedStreamPublisher | None = None
        self._last_update_published_ns: int | None = None

    async def run(self) -> None:
        """Run the tracking worker until it is stopped."""

        loop = asyncio.get_running_loop()
        attempt = 0
        try:
            while not self._stop_event.is_set():
                try:
                    await asyncio.to_thread(self._process_tracking_session, loop)
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
                        "Tracking worker for %s failed: %s. Retrying in %.2fs.",
                        self._config.camera_id,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
        except StreamDeadError as exc:
            self._record_last_error(str(exc))
            self._logger.error("%s", exc)
        finally:
            self._close_publisher()

    async def stop(self) -> None:
        """Stop the tracking worker."""

        self._stop_event.set()

    def metrics(self) -> TrackingWorkerMetrics:
        """Return a copy of the current tracking metrics."""

        with self._metrics_lock:
            return replace(self._metrics)

    def _process_tracking_session(self, loop: asyncio.AbstractEventLoop) -> None:
        av_module = _import_av()
        container = av_module.open(
            self._config.source_rtsp_url,
            mode="r",
            timeout=(self._config.open_timeout_seconds, self._config.read_timeout_seconds),
            options={
                "rtsp_transport": self._config.rtsp_transport,
                "fflags": "nobuffer",
                "flags": "low_delay",
                "reorder_queue_size": "0",
            },
        )
        try:
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"
            for packet in container.demux(stream):
                if self._stop_event.is_set():
                    return
                for frame in packet.decode():
                    if self._stop_event.is_set():
                        return
                    if not self._sampling_gate.should_emit():
                        continue
                    frame_array = frame.to_ndarray(format="bgr24")
                    tracks = self._track_frame(frame_array)
                    if self._publish_gate.should_emit():
                        self._ensure_publisher(frame_array)
                        if self._publisher is not None:
                            self._publisher.publish(frame_array)
                            self._record_published_frame()
                    if self._should_publish_update():
                        loop.call_soon_threadsafe(self._publish_update_to_loop, tracks)
        finally:
            container.close()

    def _track_frame(self, frame: np.ndarray) -> list[TrackingTrackSnapshot]:
        detections = self._detector.detect(frame)
        raw_detections = [
            ([det.left, det.top, det.width, det.height], det.confidence, det.class_name)
            for det in detections
        ]
        tracks = self._tracker.update_tracks(raw_detections, frame=frame)
        visible_tracks: list[TrackingTrackSnapshot] = []
        for track in tracks:
            if not track.is_confirmed() or track.time_since_update != 0:
                continue
            left, top, width, height = [int(round(value)) for value in track.to_ltwh(orig=True)]
            confidence = float(track.get_det_conf() or 0.0)
            similarity = None
            feature = track.get_feature()
            if feature is not None:
                similarity = self._assign_identity(track, feature)
            self._draw_track(
                frame,
                left=left,
                top=top,
                width=width,
                height=height,
                local_track_id=str(track.track_id),
                persistent_id=getattr(track, "persistent_id", None),
                confidence=confidence,
            )
            visible_tracks.append(
                TrackingTrackSnapshot(
                    track_id=str(track.track_id),
                    persistent_id=getattr(track, "persistent_id", None),
                    class_name=track.get_det_class(),
                    confidence=confidence,
                    similarity=similarity,
                    left=left,
                    top=top,
                    width=width,
                    height=height,
                ),
            )
        self._record_processed_frame(visible_tracks)
        return visible_tracks

    def _assign_identity(self, track: Any, feature: np.ndarray) -> float | None:
        persistent_id = getattr(track, "persistent_id", None)
        last_synced_ns = getattr(track, "identity_last_synced_at_monotonic_ns", None)
        now_ns = monotonic_ns()
        if persistent_id is None:
            match = self._identity_store.resolve_identity(
                camera_id=self._config.camera_id,
                stream_name=self._config.source_stream_name,
                local_track_id=str(track.track_id),
                embedding=feature,
            )
            track.set_persistent_identity(
                match.identity_id,
                similarity=match.similarity,
                synced_at_monotonic_ns=now_ns,
            )
            return match.similarity

        sync_interval_ns = 1_000_000_000
        if self._config.identity_sync_interval_seconds > 0:
            sync_interval_ns = int(self._config.identity_sync_interval_seconds * 1_000_000_000)
        if last_synced_ns is None or now_ns - last_synced_ns >= sync_interval_ns:
            self._identity_store.refresh_identity(
                identity_id=persistent_id,
                camera_id=self._config.camera_id,
                stream_name=self._config.source_stream_name,
                local_track_id=str(track.track_id),
                embedding=feature,
            )
            track.set_persistent_identity(
                persistent_id,
                similarity=getattr(track, "persistent_similarity", None),
                synced_at_monotonic_ns=now_ns,
            )
        return getattr(track, "persistent_similarity", None)

    def _ensure_publisher(self, frame: np.ndarray) -> None:
        frame_height, frame_width = frame.shape[:2]
        if self._publisher is not None and self._publisher.matches(frame_width, frame_height):
            return
        self._close_publisher()
        self._publisher = _AnnotatedStreamPublisher(
            ffmpeg_binary=self._config.ffmpeg_binary,
            publish_rtsp_url=self._config.annotated_publish_rtsp_url,
            width=frame_width,
            height=frame_height,
            fps=self._config.output_fps,
            transport=self._config.rtsp_transport,
        )

    def _close_publisher(self) -> None:
        if self._publisher is None:
            return
        self._publisher.close()
        self._publisher = None

    def _publish_update_to_loop(self, tracks: list[TrackingTrackSnapshot]) -> None:
        asyncio.create_task(
            self._publish_update_safely(tracks),
        )

    async def _publish_update_safely(self, tracks: list[TrackingTrackSnapshot]) -> None:
        try:
            await self._update_publisher.publish(
                camera_id=self._config.camera_id,
                stream_name=self._config.source_stream_name,
                annotated_stream_name=self._config.annotated_stream_name,
                tracks=tracks,
            )
        except Exception as exc:  # pylint: disable=broad-except
            self._record_last_error(str(exc))
            self._logger.warning(
                "Tracking update publishing failed for %s: %s",
                self._config.camera_id,
                exc,
            )

    def _should_publish_update(self) -> bool:
        candidate_ns = monotonic_ns()
        if (
            self._last_update_published_ns is None
            or candidate_ns - self._last_update_published_ns
            >= int(self._config.publish_update_interval_seconds * 1_000_000_000)
        ):
            self._last_update_published_ns = candidate_ns
            return True
        return False

    def _record_processed_frame(self, tracks: list[TrackingTrackSnapshot]) -> None:
        with self._metrics_lock:
            self._metrics.processed_frames += 1
            self._metrics.active_tracks = len(tracks)
            self._metrics.last_frame_at = datetime.now(timezone.utc)
            self._metrics.tracks = list(tracks)

    def _record_published_frame(self) -> None:
        with self._metrics_lock:
            self._metrics.published_frames += 1

    def _record_reconnect_failure(self, exc: Exception, attempt: int) -> None:
        with self._metrics_lock:
            self._metrics.reconnect_attempts = attempt
            self._metrics.last_error = str(exc)

    def _record_last_error(self, message: str) -> None:
        with self._metrics_lock:
            self._metrics.last_error = message

    @staticmethod
    def _draw_track(
        frame: np.ndarray,
        *,
        left: int,
        top: int,
        width: int,
        height: int,
        local_track_id: str,
        persistent_id: str | None,
        confidence: float,
    ) -> None:
        color = _color_for_identity(persistent_id or local_track_id)
        # OpenCV exposes drawing primitives dynamically, which pylint cannot introspect.
        # pylint: disable=no-member
        cv2.rectangle(frame, (left, top), (left + width, top + height), color, 2)
        label = (
            f"{persistent_id or 'new'} | local:{local_track_id} | {confidence:.2f}"
        )
        cv2.putText(
            frame,
            label,
            (left, max(24, top - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )


class _AnnotatedStreamPublisher:
    """Publish annotated raw frames to MediaMTX through FFmpeg."""

    def __init__(
        self,
        *,
        ffmpeg_binary: str,
        publish_rtsp_url: str,
        width: int,
        height: int,
        fps: float,
        transport: str,
    ) -> None:
        # The subprocess is intentionally long-lived because it owns
        # the annotated RTSP publish session.
        # pylint: disable=consider-using-with
        self._width = width
        self._height = height
        self._process = subprocess.Popen(
            build_ffmpeg_rtsp_publish_command(
                ffmpeg_binary,
                publish_rtsp_url,
                width=width,
                height=height,
                fps=fps,
                transport=transport,
            ),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def matches(self, width: int, height: int) -> bool:
        return (
            self._width == width
            and self._height == height
            and self._process.poll() is None
        )

    def publish(self, frame: np.ndarray) -> None:
        if self._process.stdin is None or self._process.poll() is not None:
            raise RuntimeError("Annotated FFmpeg publisher is not available.")
        self._process.stdin.write(frame.tobytes())

    def close(self) -> None:
        if self._process.stdin is not None:
            self._process.stdin.close()
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)


def _import_av() -> Any:
    return importlib.import_module("av")


def _color_for_identity(identity: str) -> tuple[int, int, int]:
    seed = abs(hash(identity))
    return (
        64 + (seed % 160),
        64 + ((seed // 7) % 160),
        64 + ((seed // 17) % 160),
    )
