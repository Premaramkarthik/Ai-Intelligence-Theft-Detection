"""Frame generation and downstream event publication."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import cv2
from pydantic import BaseModel, Field

from src.core.logger.logger import get_logger
from src.opencv_pipeline.contracts import IdentityLifecycleEvent, MotionSummary, PipelineOutput
from src.schemas.common import WebSocketEnvelope, utc_now
from src.services.presentation.websocket_manager import WebSocketManager
from src.services.tracking.contracts import TrackingTrackSnapshot
from src.services.tracking.updates import TrackingUpdatePublisher

if TYPE_CHECKING:
    from src.services.webrtc.registry import WebRTCRegistry


@dataclass(slots=True)
class _InferenceRecord:
    label: str
    score: float
    alert_level: str
    recorded_at: datetime


@dataclass(slots=True)
class _TrackOverlayState:
    left: float
    top: float
    width: float
    height: float
    last_seen_at: datetime


class InferenceOverlayCache:
    """Store the latest inference result per (camera_id, local_track_id)."""

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], _InferenceRecord] = {}

    def record(self, camera_id: str, local_track_id: str, label: str, score: float, alert_level: str) -> None:
        self._data[(camera_id, local_track_id)] = _InferenceRecord(
            label,
            score,
            alert_level,
            utc_now(),
        )

    def get(self, camera_id: str, local_track_id: str) -> _InferenceRecord | None:
        return self._data.get((camera_id, local_track_id))

    def items_for_camera(
        self,
        camera_id: str,
        active_track_ids: set[str] | None = None,
    ) -> list[tuple[str, _InferenceRecord]]:
        return [
            (local_track_id, record)
            for (record_camera_id, local_track_id), record in self._data.items()
            if record_camera_id == camera_id
            and (active_track_ids is None or local_track_id in active_track_ids)
        ]

    def retain_active_tracks(self, camera_id: str, active_track_ids: set[str]) -> None:
        """Remove prediction records for tracks that are no longer visible."""

        for key in [k for k in self._data if k[0] == camera_id and k[1] not in active_track_ids]:
            del self._data[key]

    def remove_camera(self, camera_id: str) -> None:
        for key in [k for k in self._data if k[0] == camera_id]:
            del self._data[key]


class CameraFrameKafkaEventPayload(BaseModel):
    """Structured event published to ``camera.frames``.

    preview_jpeg_base64 is intentionally absent: video is now delivered via WebRTC.
    """

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
    """Draw track, identity, and inference metadata onto an output frame."""

    _BOX_SMOOTHING_ALPHA = 0.55
    _BOX_RESET_DISTANCE_FACTOR = 0.75

    def __init__(self, inference_cache: InferenceOverlayCache | None = None) -> None:
        self._inference_cache = inference_cache
        self._track_overlays: dict[tuple[str, str], _TrackOverlayState] = {}

    def annotate(self, output: PipelineOutput) -> Any:
        camera_id = output.processed_frame.packet.camera_id
        frame = output.processed_frame.working_bgr.copy()
        active_track_ids = {track.track_id for track in output.tracks}
        self._retain_active_track_overlays(camera_id, active_track_ids)
        if self._inference_cache is not None:
            self._inference_cache.retain_active_tracks(camera_id, active_track_ids)

        for track in output.tracks:
            left, top, width, height = _clamp_box(
                self._stable_box(camera_id, track),
                frame.shape[1],
                frame.shape[0],
            )
            cv2.rectangle(frame, (left, top), (left + width, top + height), (30, 200, 70), 2)
            id_label = f"person_{track.track_id}"
            _draw_text_with_background(
                frame,
                f"{id_label} {track.confidence:.2f}",
                (left, max(24, top - 8)),
            )
            inference_record = (
                self._inference_cache.get(camera_id, track.track_id)
                if self._inference_cache is not None
                else None
            )
            if inference_record is not None:
                _draw_text_with_background(
                    frame,
                    (
                        f"prediction: {inference_record.label}  "
                        f"value: {inference_record.score:.4f}"
                    ),
                    (left, min(frame.shape[0] - 8, top + height + 22)),
                )

        if self._inference_cache is not None:
            self._draw_prediction_panel(frame, camera_id, active_track_ids)
        return frame

    def remove_camera(self, camera_id: str) -> None:
        """Clear stable overlay state for a removed camera."""

        for key in [k for k in self._track_overlays if k[0] == camera_id]:
            del self._track_overlays[key]

    def _retain_active_track_overlays(self, camera_id: str, active_track_ids: set[str]) -> None:
        for key in [k for k in self._track_overlays if k[0] == camera_id and k[1] not in active_track_ids]:
            del self._track_overlays[key]

    def _stable_box(self, camera_id: str, track: Any) -> tuple[int, int, int, int]:
        """Return a smoothed box for a stable overlay container."""

        key = (camera_id, track.track_id)
        state = self._track_overlays.get(key)
        now = utc_now()
        if state is None:
            state = _TrackOverlayState(
                left=float(track.left),
                top=float(track.top),
                width=float(track.width),
                height=float(track.height),
                last_seen_at=now,
            )
            self._track_overlays[key] = state
        elif self._should_reset_box(state, track):
            state.left = float(track.left)
            state.top = float(track.top)
            state.width = float(track.width)
            state.height = float(track.height)
            state.last_seen_at = now
        else:
            alpha = self._BOX_SMOOTHING_ALPHA
            state.left = _blend(state.left, float(track.left), alpha)
            state.top = _blend(state.top, float(track.top), alpha)
            state.width = _blend(state.width, float(track.width), alpha)
            state.height = _blend(state.height, float(track.height), alpha)
            state.last_seen_at = now
        return (
            int(round(state.left)),
            int(round(state.top)),
            max(1, int(round(state.width))),
            max(1, int(round(state.height))),
        )

    def _should_reset_box(self, state: _TrackOverlayState, track: Any) -> bool:
        previous_center_x = state.left + state.width / 2.0
        previous_center_y = state.top + state.height / 2.0
        current_center_x = float(track.left) + float(track.width) / 2.0
        current_center_y = float(track.top) + float(track.height) / 2.0
        distance = (
            (current_center_x - previous_center_x) ** 2
            + (current_center_y - previous_center_y) ** 2
        ) ** 0.5
        reset_distance = (
            max(state.width, state.height, float(track.width), float(track.height), 1.0)
            * self._BOX_RESET_DISTANCE_FACTOR
        )
        return distance > reset_distance

    def _draw_prediction_panel(
        self,
        frame: Any,
        camera_id: str,
        active_track_ids: set[str],
    ) -> None:
        """Render latest active prediction labels in the top-left corner."""

        prediction_items = self._inference_cache.items_for_camera(camera_id, active_track_ids)
        if not prediction_items:
            return

        sorted_items = sorted(
            prediction_items,
            key=lambda item: item[1].score,
            reverse=True,
        )
        y = 24
        for local_track_id, record in sorted_items[:5]:
            text = (
                f"prediction: {record.label}  "
                f"value: {record.score:.4f}  "
                f"track: {local_track_id}"
            )
            _draw_text_with_background(frame, text, (12, y))
            y += 24


class OutputDispatcher:
    """Publish pipeline outputs to Kafka, WebSocket metadata, and WebRTC tracks."""

    def __init__(
        self,
        tracking_update_publisher: TrackingUpdatePublisher,
        *,
        frame_publisher: Any | None,
        identity_event_publisher: Any | None,
        ws_frame_publisher: WebSocketManager | None = None,
        webrtc_registry: WebRTCRegistry | None = None,
        annotated_stream_suffix: str = "tracked",
        display_enabled: bool = False,
        display_window_prefix: str = "OpenCV Pipeline",
    ) -> None:
        self._tracking_update_publisher = tracking_update_publisher
        self._frame_publisher = frame_publisher
        self._identity_event_publisher = identity_event_publisher
        self._ws_frame_publisher = ws_frame_publisher
        self._webrtc_registry = webrtc_registry
        self._annotated_stream_suffix = annotated_stream_suffix
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

        frame_payload = CameraFrameKafkaEventPayload(
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
        )

        # Push the annotated frame to all active WebRTC viewers (non-blocking).
        if self._webrtc_registry is not None:
            self._webrtc_registry.push_frame(packet.camera_id, output.annotated_bgr)

        if self._frame_publisher is not None:
            tasks.append(self._frame_publisher.publish(frame_payload.model_dump(mode="json")))

        if self._ws_frame_publisher is not None:
            tasks.append(
                self._ws_frame_publisher.broadcast(
                    WebSocketEnvelope(
                        type="camera.frame",
                        topic="camera.frames",
                        message="Camera frame published.",
                        camera_id=packet.camera_id,
                        data=frame_payload.model_dump(mode="json"),
                    )
                )
            )

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


def _blend(previous: float, current: float, alpha: float) -> float:
    return previous + (current - previous) * alpha


def _clamp_box(
    box: tuple[int, int, int, int],
    frame_width: int,
    frame_height: int,
) -> tuple[int, int, int, int]:
    left, top, width, height = box
    left = max(0, min(left, max(0, frame_width - 1)))
    top = max(0, min(top, max(0, frame_height - 1)))
    width = max(1, min(width, max(1, frame_width - left)))
    height = max(1, min(height, max(1, frame_height - top)))
    return left, top, width, height


def _draw_text_with_background(
    frame: Any,
    text: str,
    origin: tuple[int, int],
    *,
    font_scale: float = 0.50,
    thickness: int = 1,
    text_color: tuple[int, int, int] = (0, 0, 0),
    background_color: tuple[int, int, int] = (255, 255, 255),
    padding: int = 4,
) -> None:
    """Draw readable overlay text using black text on a light background."""

    font = cv2.FONT_HERSHEY_SIMPLEX
    (text_width, text_height), baseline = cv2.getTextSize(
        text,
        font,
        font_scale,
        thickness,
    )
    x, y = origin
    top = max(0, y - text_height - padding)
    bottom = min(frame.shape[0], y + baseline + padding)
    left = max(0, x - padding)
    right = min(frame.shape[1], x + text_width + padding)
    cv2.rectangle(
        frame,
        (left, top),
        (right, bottom),
        background_color,
        thickness=-1,
    )
    cv2.putText(
        frame,
        text,
        (x, y),
        font,
        font_scale,
        text_color,
        thickness,
        cv2.LINE_AA,
    )
