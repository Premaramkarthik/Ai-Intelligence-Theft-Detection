"""Tracking worker that annotates a second MediaMTX stream with tracked person IDs."""

from __future__ import annotations

import asyncio
import importlib
import subprocess
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from time import monotonic_ns
from typing import Any

import cv2
import numpy as np

from src.core.logger.logger import get_logger
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
from src.services.tracking.contracts import PersonDetector
from src.services.tracking.identity.milvus_store import MilvusIdentityStore
from src.services.tracking.reid.embedder import TrackingReIdEmbedder
from src.services.tracking.trackers.bytetrack import (
    RoboflowByteTrackPersonTracker,
    TrackedPerson,
)
from src.services.tracking.updates import (
    NullTrackingUpdatePublisher,
    TrackingUpdatePublisher,
)
from src.utils.ffmpeg import build_ffmpeg_rtsp_publish_command
from src.utils.image import clamp_ltwh_to_frame, crop_ltwh


@dataclass(slots=True)
class _PersistentTrackIdentity:
    persistent_id: str
    similarity: float | None
    last_synced_ns: int
    last_seen_ns: int


class RealtimeTrackingWorker:  # pylint: disable=too-many-instance-attributes,too-many-arguments,too-many-positional-arguments
    """Decode, track, annotate, and republish one camera stream."""

    def __init__(
        self,
        config: TrackingWorkerConfig,
        detector: PersonDetector,
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
        self._tracker = RoboflowByteTrackPersonTracker(
            frame_rate=config.sample_fps,
            lost_track_buffer=config.tracker_lost_track_buffer,
            track_activation_threshold=config.tracker_activation_threshold,
            minimum_consecutive_frames=config.tracker_minimum_consecutive_frames,
            minimum_iou_threshold=config.tracker_minimum_iou_threshold,
            high_conf_det_threshold=config.tracker_high_conf_det_threshold,
        )
        self._reid_embedder = TrackingReIdEmbedder(
            config.embedder_name,
            weights_path=embedder_weights_path,
        )
        self._publisher: _AnnotatedStreamPublisher | None = None
        self._last_update_published_ns: int | None = None
        self._persistent_identities: dict[str, _PersistentTrackIdentity] = {}
        self._identity_sync_interval_ns = 1_000_000_000
        if config.identity_sync_interval_seconds > 0:
            self._identity_sync_interval_ns = int(
                config.identity_sync_interval_seconds * 1_000_000_000,
            )
        self._local_identity_ttl_ns = int(
            max(
                10.0,
                (
                    config.tracker_lost_track_buffer
                    / max(config.sample_fps, 0.1)
                )
                * 2.0,
            )
            * 1_000_000_000,
        )

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
        self._tracker.reset()
        self._persistent_identities.clear()
        self._last_update_published_ns = None
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
        tracks = self._tracker.update(detections)
        prepared_tracks = _prepare_tracks_for_embedding(
            frame,
            tracks,
            track_ids_requiring_embedding={
                track.track_id
                for track in tracks
                if self._should_refresh_identity(track.track_id)
            },
        )
        embeddings = self._reid_embedder.embed(
            [
                prepared_track.crop
                for prepared_track in prepared_tracks
                if prepared_track.crop is not None and prepared_track.needs_identity_refresh
            ],
        )
        embedding_index = 0
        visible_tracks: list[TrackingTrackSnapshot] = []
        for prepared_track in prepared_tracks:
            persistent_id = None
            similarity = None
            if prepared_track.crop is not None and prepared_track.needs_identity_refresh:
                identity = self._upsert_identity(
                    prepared_track.track.track_id,
                    embeddings[embedding_index],
                )
                embedding_index += 1
                persistent_id = identity.persistent_id
                similarity = identity.similarity
            else:
                identity = self._touch_identity(prepared_track.track.track_id)
                if identity is not None:
                    persistent_id = identity.persistent_id
                    similarity = identity.similarity
            self._draw_track(
                frame,
                left=prepared_track.left,
                top=prepared_track.top,
                width=prepared_track.width,
                height=prepared_track.height,
                local_track_id=prepared_track.track.track_id,
                persistent_id=persistent_id,
                confidence=prepared_track.track.confidence,
            )
            visible_tracks.append(
                TrackingTrackSnapshot(
                    track_id=prepared_track.track.track_id,
                    persistent_id=persistent_id,
                    class_name=prepared_track.track.class_name,
                    confidence=prepared_track.track.confidence,
                    similarity=similarity,
                    left=prepared_track.left,
                    top=prepared_track.top,
                    width=prepared_track.width,
                    height=prepared_track.height,
                ),
            )
        self._prune_stale_identities()
        self._record_processed_frame(visible_tracks)
        return visible_tracks

    def _should_refresh_identity(self, local_track_id: str) -> bool:
        existing = self._persistent_identities.get(local_track_id)
        if existing is None:
            return True
        if self._identity_sync_interval_ns <= 0:
            return False
        return monotonic_ns() - existing.last_synced_ns >= self._identity_sync_interval_ns

    def _upsert_identity(
        self,
        local_track_id: str,
        feature: np.ndarray,
    ) -> _PersistentTrackIdentity:
        now_ns = monotonic_ns()
        existing = self._persistent_identities.get(local_track_id)
        if existing is None:
            identity = self._resolve_new_identity(
                local_track_id=local_track_id,
                feature=feature,
                now_ns=now_ns,
            )
            self._persistent_identities[local_track_id] = identity
            return identity

        if (
            self._identity_sync_interval_ns > 0
            and now_ns - existing.last_synced_ns >= self._identity_sync_interval_ns
        ):
            if existing.persistent_id.startswith("local-"):
                existing = self._resolve_new_identity(
                    local_track_id=local_track_id,
                    feature=feature,
                    now_ns=now_ns,
                )
                self._persistent_identities[local_track_id] = existing
                return existing
            try:
                self._identity_store.refresh_identity(
                    identity_id=existing.persistent_id,
                    camera_id=self._config.camera_id,
                    stream_name=self._config.source_stream_name,
                    local_track_id=local_track_id,
                    embedding=feature,
                )
            except Exception as exc:  # pylint: disable=broad-except
                self._logger.warning(
                    "Failed to refresh persistent identity for %s/%s: %s",
                    self._config.camera_id,
                    local_track_id,
                    exc,
                )
            existing = replace(
                existing,
                last_synced_ns=now_ns,
                last_seen_ns=now_ns,
            )
        else:
            existing = replace(existing, last_seen_ns=now_ns)
        self._persistent_identities[local_track_id] = existing
        return existing

    def _resolve_new_identity(
        self,
        *,
        local_track_id: str,
        feature: np.ndarray,
        now_ns: int,
    ) -> _PersistentTrackIdentity:
        try:
            match = self._identity_store.resolve_identity(
                camera_id=self._config.camera_id,
                stream_name=self._config.source_stream_name,
                local_track_id=local_track_id,
                embedding=feature,
            )
        except Exception as exc:  # pylint: disable=broad-except
            self._logger.warning(
                "Failed to resolve persistent identity for %s/%s: %s",
                self._config.camera_id,
                local_track_id,
                exc,
            )
            return _PersistentTrackIdentity(
                persistent_id=f"local-{local_track_id}",
                similarity=None,
                last_synced_ns=now_ns,
                last_seen_ns=now_ns,
            )
        return _PersistentTrackIdentity(
            persistent_id=match.identity_id,
            similarity=match.similarity,
            last_synced_ns=now_ns,
            last_seen_ns=now_ns,
        )

    def _touch_identity(
        self,
        local_track_id: str,
    ) -> _PersistentTrackIdentity | None:
        existing = self._persistent_identities.get(local_track_id)
        if existing is None:
            return None
        touched = replace(existing, last_seen_ns=monotonic_ns())
        self._persistent_identities[local_track_id] = touched
        return touched

    def _prune_stale_identities(self) -> None:
        now_ns = monotonic_ns()
        stale_track_ids = [
            local_track_id
            for local_track_id, identity in self._persistent_identities.items()
            if now_ns - identity.last_seen_ns >= self._local_identity_ttl_ns
        ]
        for local_track_id in stale_track_ids:
            self._persistent_identities.pop(local_track_id, None)

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


class _AnnotatedStreamPublisher:  # pylint: disable=too-many-arguments
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
    ) -> None:  # pylint: disable=too-many-arguments
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
        """Return whether the publisher matches the requested frame geometry."""

        return (
            self._width == width
            and self._height == height
            and self._process.poll() is None
        )

    def publish(self, frame: np.ndarray) -> None:
        """Push one annotated frame into the FFmpeg subprocess."""

        if self._process.stdin is None or self._process.poll() is not None:
            raise RuntimeError("Annotated FFmpeg publisher is not available.")
        self._process.stdin.write(frame.tobytes())

    def close(self) -> None:
        """Terminate the FFmpeg subprocess and close its stdin pipe."""

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
    """Import PyAV lazily for the tracking session worker."""

    return importlib.import_module("av")


def _color_for_identity(identity: str) -> tuple[int, int, int]:
    """Derive a stable highlight color for a track or persistent identity."""

    seed = abs(hash(identity))
    return (
        64 + (seed % 160),
        64 + ((seed // 7) % 160),
        64 + ((seed // 17) % 160),
    )


@dataclass(slots=True, frozen=True)
class _PreparedTrackedPerson:
    track: TrackedPerson
    left: int
    top: int
    width: int
    height: int
    needs_identity_refresh: bool
    crop: np.ndarray | None


def _prepare_tracks_for_embedding(
    frame: np.ndarray,
    tracks: list[TrackedPerson],
    *,
    track_ids_requiring_embedding: set[str],
) -> list[_PreparedTrackedPerson]:
    prepared_tracks: list[_PreparedTrackedPerson] = []
    for track in tracks:
        left, top, width, height = clamp_ltwh_to_frame(
            frame.shape[:2],
            track.left,
            track.top,
            track.width,
            track.height,
        )
        if width <= 0 or height <= 0:
            continue
        needs_identity_refresh = track.track_id in track_ids_requiring_embedding
        prepared_tracks.append(
            _PreparedTrackedPerson(
                track=track,
                left=left,
                top=top,
                width=width,
                height=height,
                needs_identity_refresh=needs_identity_refresh,
                crop=crop_ltwh(frame, left, top, width, height),
            ),
        )
    return prepared_tracks
