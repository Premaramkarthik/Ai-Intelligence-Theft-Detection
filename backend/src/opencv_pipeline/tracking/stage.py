"""ByteTrack wrapper stage that turns detections into persistent local tracks."""

from __future__ import annotations

from src.core.logger.logger import get_logger
from src.opencv_pipeline.contracts import Detection, TrackedObject
from src.services.tracking.contracts import PersonDetection
from src.services.tracking.trackers.bytetrack import RoboflowByteTrackPersonTracker


class ByteTrackStage:
    """Own one Roboflow ByteTrack instance per camera stream."""

    def __init__(
        self,
        *,
        frame_rate: float,
        lost_track_buffer: int,
        track_activation_threshold: float,
        minimum_consecutive_frames: int,
        minimum_iou_threshold: float,
        high_conf_det_threshold: float,
    ) -> None:
        self._frame_rate = frame_rate
        self._lost_track_buffer = lost_track_buffer
        self._track_activation_threshold = track_activation_threshold
        self._minimum_consecutive_frames = minimum_consecutive_frames
        self._minimum_iou_threshold = minimum_iou_threshold
        self._high_conf_det_threshold = high_conf_det_threshold
        self._trackers: dict[str, RoboflowByteTrackPersonTracker] = {}
        self._logger = get_logger(__name__)

    def update(
        self,
        *,
        camera_id: str,
        stream_name: str,
        detections: list[Detection],
    ) -> list[TrackedObject]:
        """Update one camera tracker and return visible tracks."""

        tracker = self._trackers.get(camera_id)
        if tracker is None:
            tracker = RoboflowByteTrackPersonTracker(
                frame_rate=self._frame_rate,
                lost_track_buffer=self._lost_track_buffer,
                track_activation_threshold=self._track_activation_threshold,
                minimum_consecutive_frames=self._minimum_consecutive_frames,
                minimum_iou_threshold=self._minimum_iou_threshold,
                high_conf_det_threshold=self._high_conf_det_threshold,
            )
            self._trackers[camera_id] = tracker
            self._logger.info(
                "Tracker initialised for camera stream.",
                extra={
                    "structured": {
                        "event": "tracker.initialized",
                        "camera_id": camera_id,
                        "stream_name": stream_name,
                        "frame_rate": self._frame_rate,
                        "lost_track_buffer": self._lost_track_buffer,
                        "track_activation_threshold": self._track_activation_threshold,
                        "minimum_consecutive_frames": self._minimum_consecutive_frames,
                        "minimum_iou_threshold": self._minimum_iou_threshold,
                        "high_conf_det_threshold": self._high_conf_det_threshold,
                    }
                },
            )

        person_detections = [
            PersonDetection(
                left=detection.left,
                top=detection.top,
                width=detection.width,
                height=detection.height,
                confidence=detection.confidence,
                class_name=detection.class_name,
            )
            for detection in detections
            if detection.class_name == "person"
        ]
        try:
            tracked_people = tracker.update(person_detections)
        except Exception:
            self._logger.exception(
                "Tracker update failed.",
                extra={
                    "structured": {
                        "event": "tracker.update_failed",
                        "camera_id": camera_id,
                        "stream_name": stream_name,
                        "input_detections": len(detections),
                        "person_detections": len(person_detections),
                    }
                },
            )
            raise
        tracked_objects = [
            TrackedObject(
                camera_id=camera_id,
                stream_name=stream_name,
                track_id=tracked_person.track_id,
                left=tracked_person.left,
                top=tracked_person.top,
                width=tracked_person.width,
                height=tracked_person.height,
                confidence=tracked_person.confidence,
                class_name=tracked_person.class_name,
                age_frames=tracked_person.age_frames,
                consecutive_hits=tracked_person.consecutive_hits,
                frames_since_update=tracked_person.frames_since_update,
            )
            for tracked_person in tracked_people
        ]
        self._logger.debug(
            "Tracker update completed.",
            extra={
                "structured": {
                    "event": "tracker.update_completed",
                    "camera_id": camera_id,
                    "stream_name": stream_name,
                    "input_detections": len(detections),
                    "person_detections": len(person_detections),
                    "active_tracks": len(tracked_objects),
                }
            },
        )
        return tracked_objects

    def remove_camera(self, camera_id: str) -> None:
        """Discard tracker state when a camera is removed from the runtime."""

        removed = self._trackers.pop(camera_id, None)
        if removed is not None:
            self._logger.info(
                "Tracker state removed for camera.",
                extra={
                    "structured": {
                        "event": "tracker.removed",
                        "camera_id": camera_id,
                    }
                },
            )

