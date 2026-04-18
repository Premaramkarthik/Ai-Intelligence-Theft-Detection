"""Annotated frame generation and downstream event publication."""

from __future__ import annotations

import base64
import asyncio
from datetime import datetime
from typing import Any

import cv2
from pydantic import BaseModel, Field

from src.core.logger.logger import get_logger
from src.opencv_pipeline.contracts import IdentityLifecycleEvent, MotionSummary, PipelineOutput
from src.schemas.common import utc_now
from src.services.tracking.contracts import TrackingTrackSnapshot
from src.services.tracking.updates import TrackingUpdatePublisher


class CameraFrameKafkaEventPayload(BaseModel):
    """Structured event published to ``camera.frames``."""

    event: str = "camera.frame"
    emitted_at: datetime = Field(default_factory=utc_now)
    camera_id: str
    stream_name: str
    sequence_number: int
    captured_at: datetime
    width: int
    height: int
    pipeline_latency_ms: float
    motion: dict[str, float | bool]
    detections: int
    active_tracks: int
    preview_jpeg_base64: str | None = None


class IdentityKafkaEventPayload(BaseModel):
    """Structured event published to ``identity.events``."""

    event: str
    occurred_at: datetime
    camera_id: str
    stream_name: str
    local_track_id: str
    persistent_id: str
    previous_persistent_id: str | None
    matched_existing: bool
    similarity: float | None
    left: int
    top: int
    width: int
    height: int
    world_x: float | None = None
    world_y: float | None = None


class FrameAnnotator:
    """Draw track, identity, and motion metadata onto an output frame."""

    def annotate(
        self,
        output: PipelineOutput,
    ) -> Any:
        frame = output.processed_frame.working_bgr.copy()
        for track in output.tracks:
            top_left = (track.left, track.top)
            bottom_right = (track.left + track.width, track.top + track.height)
            cv2.rectangle(frame, top_left, bottom_right, (30, 200, 70), 2)
            label = track.persistent_id or track.track_id
            cv2.putText(
                frame,
                f"{label} {track.confidence:.2f}",
                (track.left, max(24, track.top - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                2,
            )

        motion = output.motion
        cv2.putText(
            frame,
            (
                f"motion={motion.mean_magnitude:.2f} "
                f"fg={motion.foreground_ratio:.2%} "
                f"tracks={len(output.tracks)}"
            ),
            (12, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 255),
            2,
        )
        return frame


class OutputDispatcher:
    """Publish pipeline outputs to Kafka and the tracking/inference fanout path."""

    def __init__(
        self,
        tracking_update_publisher: TrackingUpdatePublisher,
        *,
        frame_publisher: Any | None,
        identity_event_publisher: Any | None,
        annotated_stream_suffix: str = "tracked",
        include_previews: bool = False,
        jpeg_quality: int = 70,
        display_enabled: bool = False,
        display_window_prefix: str = "OpenCV Pipeline",
    ) -> None:
        self._tracking_update_publisher = tracking_update_publisher
        self._frame_publisher = frame_publisher
        self._identity_event_publisher = identity_event_publisher
        self._annotated_stream_suffix = annotated_stream_suffix
        self._include_previews = include_previews
        self._jpeg_quality = jpeg_quality
        self._display_enabled = display_enabled
        self._display_window_prefix = display_window_prefix
        self._logger = get_logger(__name__)

    async def publish(self, output: PipelineOutput) -> None:
        """Publish one processed frame's tracking, frame, and identity events."""

        processed_frame = output.processed_frame
        packet = processed_frame.packet
        annotated_stream_name = f"{packet.stream_name}_{self._annotated_stream_suffix}"

        tracking_snapshot = [
            TrackingTrackSnapshot(
                track_id=track.track_id,
                persistent_id=track.persistent_id,
                class_name=track.class_name,
                confidence=track.confidence,
                similarity=track.similarity,
                left=track.left,
                top=track.top,
                width=track.width,
                height=track.height,
                sampled_at=packet.captured_at,
                age_frames=track.age_frames,
                consecutive_hits=track.consecutive_hits,
                frames_since_update=track.frames_since_update,
                persistent_id_state=track.persistent_id_state.value,
            )
            for track in output.tracks
        ]
        tasks = [
            self._tracking_update_publisher.publish(
                camera_id=packet.camera_id,
                stream_name=packet.stream_name,
                annotated_stream_name=annotated_stream_name,
                tracks=tracking_snapshot,
                frame=processed_frame.working_bgr,
            ),
            self.publish_identity_events(output.identity_events),
        ]

        if self._frame_publisher is not None:
            payload = CameraFrameKafkaEventPayload(
                camera_id=packet.camera_id,
                stream_name=packet.stream_name,
                sequence_number=packet.sequence_number,
                captured_at=packet.captured_at,
                width=output.annotated_bgr.shape[1],
                height=output.annotated_bgr.shape[0],
                pipeline_latency_ms=output.pipeline_latency_ms,
                motion=_motion_payload(output.motion),
                detections=len(output.detections),
                active_tracks=len(output.tracks),
                preview_jpeg_base64=(
                    _encode_frame_preview(output.annotated_bgr, self._jpeg_quality)
                    if self._include_previews
                    else None
                ),
            )
            tasks.append(self._frame_publisher.publish(payload.model_dump(mode="json")))

        self._render_preview(packet.camera_id, packet.stream_name, output.annotated_bgr)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                self._logger.warning(
                    "OpenCV output publish failed for camera %s: %s",
                    packet.camera_id,
                    result,
                )

    async def publish_identity_events(
        self,
        events: list[IdentityLifecycleEvent],
    ) -> None:
        """Publish identity lifecycle events independently from frame outputs."""

        if self._identity_event_publisher is None or not events:
            return

        tasks = [
            self._identity_event_publisher.publish(
                IdentityKafkaEventPayload(
                    event=event.event_type.value,
                    occurred_at=event.occurred_at,
                    camera_id=event.camera_id,
                    stream_name=event.stream_name,
                    local_track_id=event.local_track_id,
                    persistent_id=event.persistent_id,
                    previous_persistent_id=event.previous_persistent_id,
                    matched_existing=event.matched_existing,
                    similarity=event.similarity,
                    left=event.left,
                    top=event.top,
                    width=event.width,
                    height=event.height,
                    world_x=event.world_x,
                    world_y=event.world_y,
                ).model_dump(mode="json")
            )
            for event in events
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for event, result in zip(events, results):
            if isinstance(result, Exception):
                self._logger.warning(
                    "Identity event publish failed for camera %s track %s: %s",
                    event.camera_id,
                    event.local_track_id,
                    result,
                )

    def close(self) -> None:
        """Release local preview windows when display mode is enabled."""

        if not self._display_enabled:
            return
        try:
            cv2.destroyAllWindows()
        except cv2.error as exc:
            self._logger.debug("OpenCV preview window cleanup failed: %s", exc)

    def _render_preview(self, camera_id: str, stream_name: str, frame_bgr: Any) -> None:
        """Render the annotated stream locally through OpenCV HighGUI."""

        if not self._display_enabled:
            return
        window_name = f"{self._display_window_prefix}: {stream_name} ({camera_id})"
        try:
            cv2.imshow(window_name, frame_bgr)
            cv2.waitKey(1)
        except cv2.error as exc:
            self._logger.warning(
                "OpenCV preview rendering failed for camera %s: %s",
                camera_id,
                exc,
            )
            self._display_enabled = False


def _motion_payload(motion: MotionSummary) -> dict[str, float | bool]:
    return {
        "mean_magnitude": motion.mean_magnitude,
        "dominant_dx": motion.dominant_dx,
        "dominant_dy": motion.dominant_dy,
        "foreground_ratio": motion.foreground_ratio,
        "is_motion_consistent": motion.is_motion_consistent,
    }


def _encode_frame_preview(frame_bgr: Any, jpeg_quality: int) -> str | None:
    ok, encoded = cv2.imencode(
        ".jpg",
        frame_bgr,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)],
    )
    if not ok:
        return None
    return base64.b64encode(encoded.tobytes()).decode("ascii")
