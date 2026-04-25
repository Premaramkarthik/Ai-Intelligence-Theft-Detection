from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Protocol

from src.core.logger.logger import get_logger
from src.schemas.common import WebSocketEnvelope
from src.services.inference.contracts import InferenceIngressSample
from src.services.inference.logging import log_inference_event, summarize_array
from src.services.presentation.websocket_manager import WebSocketManager
from src.services.tracking.contracts import TrackingTrackSnapshot
from src.utils.image import crop_ltwh


class TrackingUpdatePublisher(Protocol):
    """Protocol implemented by tracking metadata broadcasters."""

    async def publish(
        self,
        *,
        camera_id: str,
        stream_name: str,
        annotated_stream_name: str,
        tracks: list[TrackingTrackSnapshot],
        frame: Any = None,
    ) -> None:
        """Publish the latest tracking state."""


class NullTrackingUpdatePublisher:
    """Discard tracking updates when no broadcaster is configured."""

    async def publish(
        self,
        *,
        camera_id: str,
        stream_name: str,
        annotated_stream_name: str,
        tracks: list[TrackingTrackSnapshot],
        frame: Any = None,
    ) -> None:
        del camera_id, stream_name, annotated_stream_name, tracks, frame


class FanoutTrackingUpdatePublisher:
    """Fan out one tracking update to multiple downstream publishers."""

    def __init__(self, publishers: Iterable[TrackingUpdatePublisher]) -> None:
        self._publishers = tuple(publishers)
        self._logger = get_logger(__name__)

    async def publish(
        self,
        *,
        camera_id: str,
        stream_name: str,
        annotated_stream_name: str,
        tracks: list[TrackingTrackSnapshot],
        frame: Any = None,
    ) -> None:
        results = await asyncio.gather(
            *(
                publisher.publish(
                    camera_id=camera_id,
                    stream_name=stream_name,
                    annotated_stream_name=annotated_stream_name,
                    tracks=tracks,
                    frame=frame,
                )
                for publisher in self._publishers
            ),
            return_exceptions=True,
        )
        for publisher, result in zip(self._publishers, results):
            if isinstance(result, Exception):
                self._logger.warning(
                    "Tracking update publisher %s failed for camera %s: %s",
                    publisher.__class__.__name__,
                    camera_id,
                    result,
                )


class WebSocketTrackingUpdatePublisher:
    """Broadcast tracking updates through the existing websocket fanout."""

    def __init__(self, websocket_manager: WebSocketManager) -> None:
        self._websocket_manager = websocket_manager

    async def publish(
        self,
        *,
        camera_id: str,
        stream_name: str,
        annotated_stream_name: str,
        tracks: list[TrackingTrackSnapshot],
        frame: Any = None,
    ) -> None:
        del frame
        await self._websocket_manager.broadcast(
            WebSocketEnvelope(
                type="tracking.updated",
                topic="tracking.updated",
                message="Tracking update available.",
                camera_id=camera_id,
                data={
                    "event": "tracking.updated",
                    "emitted_at": datetime.now(timezone.utc).isoformat(),
                    "camera_id": camera_id,
                    "stream_name": stream_name,
                    "annotated_stream_name": annotated_stream_name,
                    "active_tracks": len(tracks),
                    "tracks": [
                        {
                            "track_id": track.track_id,
                            "persistent_id": track.persistent_id,
                            "class_name": track.class_name,
                            "confidence": track.confidence,
                            "similarity": track.similarity,
                            "left": track.left,
                            "top": track.top,
                            "width": track.width,
                            "height": track.height,
                            "sampled_at": track.sampled_at.isoformat(),
                            "age_frames": track.age_frames,
                            "consecutive_hits": track.consecutive_hits,
                            "frames_since_update": track.frames_since_update,
                            "persistent_id_state": track.persistent_id_state,
                        }
                        for track in tracks
                    ],
                },
            ),
        )


class _InferenceIngress(Protocol):
    """Structural protocol satisfied by ``InferenceManager.ingest_sample``."""

    def is_camera_enabled(self, camera_id: str) -> bool:
        """Return whether inference ingress is currently active for a camera."""

    def ingest_sample(self, sample: InferenceIngressSample) -> None:
        """Dispatch one sample into the inference ingress pipeline."""


class InferenceIngressPublisher:
    """Forward eligible tracking crops into the inference ingress pipeline.

    Implements ``TrackingUpdatePublisher`` and sits alongside the WebSocket
    and Kafka publishers inside ``FanoutTrackingUpdatePublisher``.  It
    receives the unannotated ``frame`` (captured before annotation drawing
    in the tracking worker), crops each track's bounding box, and routes
    the resulting ``InferenceIngressSample`` to ``InferenceManager`` which
    delegates to the per-camera ``InferenceIngressScheduler``.  The
    scheduler's dispatch gate applies the final quality checks.
    """

    _STATE_LOG_INTERVAL_SECONDS = 30.0

    def __init__(self, ingress: _InferenceIngress) -> None:
        self._ingress = ingress
        self._logger = get_logger(__name__)
        self._last_visible_state: dict[str, tuple[str, float]] = {}

    def _log_visible_state(
        self,
        *,
        camera_id: str,
        state: str,
        event: str,
        message: str,
        **fields: object,
    ) -> None:
        now = monotonic()
        previous = self._last_visible_state.get(camera_id)
        if previous is not None:
            previous_state, previous_logged_at = previous
            if previous_state == state and (
                now - previous_logged_at < self._STATE_LOG_INTERVAL_SECONDS
            ):
                return
        self._last_visible_state[camera_id] = (state, now)
        log_inference_event(
            self._logger,
            logging.INFO,
            event,
            message,
            camera_id=camera_id,
            **fields,
        )

    async def publish(
        self,
        *,
        camera_id: str,
        stream_name: str,
        annotated_stream_name: str,
        tracks: list[TrackingTrackSnapshot],
        frame: Any = None,
    ) -> None:
        del annotated_stream_name
        if not self._ingress.is_camera_enabled(camera_id):
            self._log_visible_state(
                camera_id=camera_id,
                state="skip:camera_inference_disabled",
                event="inference.input_skipped",
                message=(
                    "Inference input skipped before scheduler: "
                    "reason=camera_inference_disabled "
                    f"camera_id={camera_id} "
                    f"stream_name={stream_name} "
                    f"total_tracks={len(tracks)}"
                ),
                stream_name=stream_name,
                total_tracks=len(tracks),
                reason="camera_inference_disabled",
            )
            log_inference_event(
                self._logger,
                logging.DEBUG,
                "inference.input_skipped",
                "Inference input skipped because the camera has no active inference worker.",
                camera_id=camera_id,
                stream_name=stream_name,
                total_tracks=len(tracks),
                reason="camera_inference_disabled",
            )
            return
        if frame is None:
            self._log_visible_state(
                camera_id=camera_id,
                state="skip:missing_frame",
                event="inference.input_skipped",
                message=(
                    "Inference input skipped before scheduler: "
                    "reason=missing_frame "
                    f"camera_id={camera_id} "
                    f"stream_name={stream_name} "
                    f"total_tracks={len(tracks)}"
                ),
                stream_name=stream_name,
                total_tracks=len(tracks),
                reason="missing_frame",
            )
            log_inference_event(
                self._logger,
                logging.DEBUG,
                "inference.input_skipped",
                "Inference input skipped because frame data was unavailable.",
                camera_id=camera_id,
                stream_name=stream_name,
                total_tracks=len(tracks),
                reason="missing_frame",
            )
            return
        if not tracks:
            self._log_visible_state(
                camera_id=camera_id,
                state="skip:no_tracks",
                event="inference.input_skipped",
                message=(
                    "Inference input skipped before scheduler: "
                    "reason=no_tracks "
                    f"camera_id={camera_id} "
                    f"stream_name={stream_name} "
                    "total_tracks=0"
                ),
                stream_name=stream_name,
                total_tracks=0,
                reason="no_tracks",
            )
            log_inference_event(
                self._logger,
                logging.DEBUG,
                "inference.input_skipped",
                "Inference input skipped because no tracks were available.",
                camera_id=camera_id,
                stream_name=stream_name,
                total_tracks=0,
                frame=summarize_array(frame),
                reason="no_tracks",
            )
            return

        log_inference_event(
            self._logger,
            logging.DEBUG,
            "inference.input_received",
            "Inference input received from tracking.",
            camera_id=camera_id,
            stream_name=stream_name,
            total_tracks=len(tracks),
            frame=summarize_array(frame),
        )
        now = datetime.now(timezone.utc)
        dispatched_tracks = 0
        for track in tracks:
            # Use the Milvus-assigned persistent_id when available; fall back to
            # track_id so inference runs even when Milvus identity isn't resolved yet.
            inference_id = track.persistent_id or track.track_id
            crop = crop_ltwh(frame, track.left, track.top, track.width, track.height)
            sample = InferenceIngressSample(
                camera_id=camera_id,
                stream_name=stream_name,
                local_track_id=track.track_id,
                persistent_id=inference_id,
                sampled_at=now,
                left=track.left,
                top=track.top,
                width=track.width,
                height=track.height,
                crop=crop,
                age_frames=track.age_frames,
                consecutive_hits=track.consecutive_hits,
                frames_since_update=track.frames_since_update,
                persistent_id_state=track.persistent_id_state,
            )
            self._ingress.ingest_sample(sample)
            dispatched_tracks += 1

        self._log_visible_state(
            camera_id=camera_id,
            state="dispatch",
            event="inference.input_dispatched_visible",
            message=(
                "Inference input dispatched to scheduler: "
                f"camera_id={camera_id} "
                f"stream_name={stream_name} "
                f"total_tracks={len(tracks)} "
                f"dispatched_tracks={dispatched_tracks} "
                f"sampled_at={now.isoformat()}"
            ),
            stream_name=stream_name,
            total_tracks=len(tracks),
            dispatched_tracks=dispatched_tracks,
            sampled_at=now.isoformat(),
        )
        log_inference_event(
            self._logger,
            logging.DEBUG,
            "inference.input_dispatched",
            "Inference input dispatch completed.",
            camera_id=camera_id,
            stream_name=stream_name,
            total_tracks=len(tracks),
            dispatched_tracks=dispatched_tracks,
            sampled_at=now.isoformat(),
        )
