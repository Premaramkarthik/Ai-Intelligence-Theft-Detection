"""Tracking worker that annotates a second MediaMTX stream with tracked person IDs."""

from __future__ import annotations

import asyncio
import importlib
import queue
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
from src.services.tracking.reid.shared_embedding_service import SharedEmbeddingService
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

# Minimum crop dimensions worth embedding (BN-3).
_MIN_CROP_WIDTH = 32
_MIN_CROP_HEIGHT = 64

# Maximum items held in the enrichment backlog queue per worker.
_ENRICHMENT_QUEUE_MAXSIZE = 64

# Maximum annotated frames queued for the FFmpeg publisher thread (BN-9).
_PUBLISH_QUEUE_MAXSIZE = 4


@dataclass(slots=True)
class _PersistentTrackIdentity:
    persistent_id: str
    similarity: float | None
    last_synced_ns: int
    last_seen_ns: int
    state: str  # "pending" | "assigned" | "local"


@dataclass(slots=True)
class _EnrichmentItem:
    """Crop queued by the tracking thread for background embedding + Milvus."""

    track_id: str
    crop: np.ndarray
    camera_id: str
    stream_name: str


class RealtimeTrackingWorker:  # pylint: disable=too-many-instance-attributes,too-many-arguments,too-many-positional-arguments
    """Decode, track, annotate, and republish one camera stream."""

    def __init__(
        self,
        config: TrackingWorkerConfig,
        detector: PersonDetector,
        identity_store: MilvusIdentityStore,
        update_publisher: TrackingUpdatePublisher | None = None,
        shared_embedding_service: SharedEmbeddingService | None = None,
    ) -> None:
        self._config = config
        self._detector = detector
        self._identity_store = identity_store
        self._update_publisher = update_publisher or NullTrackingUpdatePublisher()
        self._shared_embedding_service = shared_embedding_service
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
        self._publisher: _BoundedAnnotatedStreamPublisher | None = None
        self._last_update_published_ns: int | None = None

        # Identity state — protected by _identities_lock (shared with enrichment thread).
        self._persistent_identities: dict[str, _PersistentTrackIdentity] = {}
        self._identities_lock = threading.Lock()

        # Enrichment queue: tracking thread writes, enrichment thread reads.
        self._enrichment_queue: queue.Queue[_EnrichmentItem] = queue.Queue(
            maxsize=_ENRICHMENT_QUEUE_MAXSIZE
        )

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

    # ------------------------------------------------------------------
    # Session loop (runs in asyncio.to_thread)
    # ------------------------------------------------------------------

    def _process_tracking_session(self, loop: asyncio.AbstractEventLoop) -> None:
        self._tracker.reset()
        with self._identities_lock:
            self._persistent_identities.clear()
        self._last_update_published_ns = None

        # Start the background enrichment thread for this session.
        enrichment_thread = threading.Thread(
            target=self._enrichment_loop,
            args=(loop,),
            daemon=True,
            name=f"tracking-enrichment:{self._config.camera_id}",
        )
        enrichment_thread.start()

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
                    tracks = self._track_frame(frame_array, loop)
                    if self._publish_gate.should_emit():
                        self._ensure_publisher(frame_array)
                        if self._publisher is not None:
                            # BN-9: non-blocking put; drops frame if queue is full.
                            self._publisher.put(frame_array)
                            self._record_published_frame()
                    if self._should_publish_update():
                        loop.call_soon_threadsafe(self._publish_update_to_loop, tracks)
        finally:
            container.close()
            enrichment_thread.join(timeout=5.0)

    # ------------------------------------------------------------------
    # Real-time tracking stage (no Milvus, no blocking embedding)
    # ------------------------------------------------------------------

    def _track_frame(
        self,
        frame: np.ndarray,
        loop: asyncio.AbstractEventLoop,
    ) -> list[TrackingTrackSnapshot]:
        detections = self._detector.detect(frame)
        tracks = self._tracker.update(detections)

        now_ns = monotonic_ns()
        visible_tracks: list[TrackingTrackSnapshot] = []

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

            # Touch last_seen without blocking.
            with self._identities_lock:
                existing = self._persistent_identities.get(track.track_id)
                if existing is not None:
                    self._persistent_identities[track.track_id] = replace(
                        existing, last_seen_ns=now_ns
                    )

            # BN-2/BN-3: queue crop for enrichment if refresh needed and crop is large enough.
            if self._should_refresh_identity(track.track_id, now_ns):
                if width >= _MIN_CROP_WIDTH and height >= _MIN_CROP_HEIGHT:
                    crop = crop_ltwh(frame, left, top, width, height)
                    try:
                        self._enrichment_queue.put_nowait(
                            _EnrichmentItem(
                                track_id=track.track_id,
                                crop=crop,
                                camera_id=self._config.camera_id,
                                stream_name=self._config.source_stream_name,
                            )
                        )
                    except queue.Full:
                        pass  # enrichment backlog full; skip this frame

            # Read current identity state (written by enrichment thread).
            with self._identities_lock:
                identity = self._persistent_identities.get(track.track_id)

            persistent_id = identity.persistent_id if identity else None
            similarity = identity.similarity if identity else None
            id_state = identity.state if identity else "pending"

            self._draw_track(
                frame,
                left=left,
                top=top,
                width=width,
                height=height,
                local_track_id=track.track_id,
                persistent_id=persistent_id,
                confidence=track.confidence,
            )
            visible_tracks.append(
                TrackingTrackSnapshot(
                    track_id=track.track_id,
                    persistent_id=persistent_id,
                    class_name=track.class_name,
                    confidence=track.confidence,
                    similarity=similarity,
                    left=left,
                    top=top,
                    width=width,
                    height=height,
                    age_frames=track.age_frames,
                    consecutive_hits=track.consecutive_hits,
                    frames_since_update=track.frames_since_update,
                    persistent_id_state=id_state,
                )
            )

        self._prune_stale_identities()
        self._record_processed_frame(visible_tracks)
        return visible_tracks

    # ------------------------------------------------------------------
    # Enrichment stage (runs in a separate daemon thread)
    # ------------------------------------------------------------------

    def _enrichment_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Pull crops from the enrichment queue, embed, and resolve Milvus identities."""

        while not self._stop_event.is_set():
            try:
                item: _EnrichmentItem = self._enrichment_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # Embed the crop using the shared service (or fall back to local-only).
            embedding = None
            if self._shared_embedding_service is not None:
                try:
                    embeddings = self._shared_embedding_service.embed_from_thread(
                        [item.crop], loop
                    )
                    embedding = embeddings[0] if embeddings else None
                except Exception as exc:  # pylint: disable=broad-except
                    self._logger.warning(
                        "Embedding failed for %s/%s: %s",
                        item.camera_id,
                        item.track_id,
                        exc,
                    )

            if embedding is None:
                # Cannot embed; mark as local so tracking continues.
                with self._identities_lock:
                    if item.track_id not in self._persistent_identities:
                        self._persistent_identities[item.track_id] = _PersistentTrackIdentity(
                            persistent_id=f"local-{item.track_id}",
                            similarity=None,
                            last_synced_ns=monotonic_ns(),
                            last_seen_ns=monotonic_ns(),
                            state="local",
                        )
                continue

            # Resolve identity in Milvus.
            now_ns = monotonic_ns()
            try:
                with self._identities_lock:
                    existing = self._persistent_identities.get(item.track_id)

                if existing is None or existing.state == "pending":
                    match = self._identity_store.resolve_identity(
                        camera_id=item.camera_id,
                        stream_name=item.stream_name,
                        local_track_id=item.track_id,
                        embedding=embedding,
                    )
                    new_state = "assigned" if match.matched_existing else "local"
                    new_identity = _PersistentTrackIdentity(
                        persistent_id=match.identity_id,
                        similarity=match.similarity,
                        last_synced_ns=now_ns,
                        last_seen_ns=now_ns,
                        state=new_state,
                    )
                else:
                    try:
                        self._identity_store.refresh_identity(
                            identity_id=existing.persistent_id,
                            camera_id=item.camera_id,
                            stream_name=item.stream_name,
                            local_track_id=item.track_id,
                            embedding=embedding,
                        )
                    except Exception as exc:  # pylint: disable=broad-except
                        self._logger.warning(
                            "Failed to refresh identity for %s/%s: %s",
                            item.camera_id,
                            item.track_id,
                            exc,
                        )
                    new_identity = replace(
                        existing,
                        last_synced_ns=now_ns,
                        last_seen_ns=now_ns,
                    )
            except Exception as exc:  # pylint: disable=broad-except
                self._logger.warning(
                    "Identity resolution failed for %s/%s: %s",
                    item.camera_id,
                    item.track_id,
                    exc,
                )
                new_identity = _PersistentTrackIdentity(
                    persistent_id=f"local-{item.track_id}",
                    similarity=None,
                    last_synced_ns=now_ns,
                    last_seen_ns=now_ns,
                    state="local",
                )

            with self._identities_lock:
                self._persistent_identities[item.track_id] = new_identity

    # ------------------------------------------------------------------
    # Identity helpers (called from tracking thread)
    # ------------------------------------------------------------------

    def _should_refresh_identity(self, local_track_id: str, now_ns: int) -> bool:
        """Return True and mark pending if this track needs an enrichment pass."""
        with self._identities_lock:
            existing = self._persistent_identities.get(local_track_id)
            if existing is None:
                # First time seen — insert a pending sentinel so we do not re-queue
                # until the enrichment interval elapses again.
                self._persistent_identities[local_track_id] = _PersistentTrackIdentity(
                    persistent_id=f"local-{local_track_id}",
                    similarity=None,
                    last_synced_ns=now_ns,
                    last_seen_ns=now_ns,
                    state="pending",
                )
                return True
            if self._identity_sync_interval_ns <= 0:
                return False
            if now_ns - existing.last_synced_ns >= self._identity_sync_interval_ns:
                # Stamp last_synced_ns now to prevent duplicate queuing.
                self._persistent_identities[local_track_id] = replace(
                    existing, last_synced_ns=now_ns
                )
                return True
        return False

    def _prune_stale_identities(self) -> None:
        now_ns = monotonic_ns()
        with self._identities_lock:
            stale = [
                tid
                for tid, identity in self._persistent_identities.items()
                if now_ns - identity.last_seen_ns >= self._local_identity_ttl_ns
            ]
            for tid in stale:
                self._persistent_identities.pop(tid, None)

    # ------------------------------------------------------------------
    # Publisher helpers
    # ------------------------------------------------------------------

    def _ensure_publisher(self, frame: np.ndarray) -> None:
        frame_height, frame_width = frame.shape[:2]
        if self._publisher is not None and self._publisher.matches(frame_width, frame_height):
            return
        self._close_publisher()
        self._publisher = _BoundedAnnotatedStreamPublisher(
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

    # ------------------------------------------------------------------
    # Update publisher helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Metrics helpers
    # ------------------------------------------------------------------

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


class _BoundedAnnotatedStreamPublisher:  # pylint: disable=too-many-arguments
    """Publish annotated raw frames to MediaMTX through FFmpeg.

    A bounded queue (max _PUBLISH_QUEUE_MAXSIZE frames) sits between the
    tracking thread and a dedicated publisher thread.  If the queue is
    full the frame is dropped so the tracker never stalls on a slow FFmpeg
    pipe (BN-9).
    """

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
        self._width = width
        self._height = height
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue(
            maxsize=_PUBLISH_QUEUE_MAXSIZE
        )
        # The subprocess is intentionally long-lived because it owns
        # the annotated RTSP publish session.
        # pylint: disable=consider-using-with
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
        self._thread = threading.Thread(
            target=self._drain,
            daemon=True,
            name="tracking-ffmpeg-publisher",
        )
        self._thread.start()

    def matches(self, width: int, height: int) -> bool:
        """Return whether the publisher matches the requested frame geometry."""

        return (
            self._width == width
            and self._height == height
            and self._process.poll() is None
        )

    def put(self, frame: np.ndarray) -> None:
        """Enqueue one annotated frame; drop it silently if the queue is full."""

        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            pass

    def close(self) -> None:
        """Stop the drain thread and terminate the FFmpeg subprocess."""

        try:
            self._queue.put_nowait(None)  # sentinel
        except queue.Full:
            pass
        self._thread.join(timeout=5.0)
        if self._process.stdin is not None:
            self._process.stdin.close()
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)

    def _drain(self) -> None:
        """Publisher thread: write frames from the queue to FFmpeg stdin."""

        while True:
            frame = self._queue.get()
            if frame is None:
                break
            if self._process.stdin is None or self._process.poll() is not None:
                break
            try:
                self._process.stdin.write(frame.tobytes())
            except OSError:
                break


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


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
