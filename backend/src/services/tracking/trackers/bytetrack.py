"""Roboflow Trackers ByteTrack adapter for person tracking."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import supervision as sv
from trackers import ByteTrackTracker

from src.services.tracking.detectors.yolo26_detector import PersonDetection


@dataclass(slots=True, frozen=True)
class TrackedPerson:
    """One tracked person returned by the ByteTrack adapter."""

    track_id: str
    class_name: str
    confidence: float
    left: int
    top: int
    width: int
    height: int


class RoboflowByteTrackPersonTracker:
    """Wrap Roboflow's ByteTrack tracker behind a person-focused interface."""

    def __init__(
        self,
        *,
        frame_rate: float,
        lost_track_buffer: int = 30,
        track_activation_threshold: float = 0.7,
        minimum_consecutive_frames: int = 2,
        minimum_iou_threshold: float = 0.1,
        high_conf_det_threshold: float = 0.6,
    ) -> None:
        self._tracker = ByteTrackTracker(
            lost_track_buffer=lost_track_buffer,
            frame_rate=frame_rate,
            track_activation_threshold=track_activation_threshold,
            minimum_consecutive_frames=minimum_consecutive_frames,
            minimum_iou_threshold=minimum_iou_threshold,
            high_conf_det_threshold=high_conf_det_threshold,
        )

    def reset(self) -> None:
        """Reset tracker state for a fresh RTSP session."""

        self._tracker.reset()

    def update(self, detections: Sequence[PersonDetection]) -> list[TrackedPerson]:
        """Track the current frame's detections and return visible tracked persons."""

        tracked_detections = self._tracker.update(_to_supervision_detections(detections))
        return _to_tracked_people(tracked_detections)


def _to_supervision_detections(
    detections: Sequence[PersonDetection],
) -> sv.Detections:
    if not detections:
        return sv.Detections.empty()

    xyxy = np.asarray(
        [
            [
                detection.left,
                detection.top,
                detection.left + detection.width,
                detection.top + detection.height,
            ]
            for detection in detections
        ],
        dtype=np.float32,
    )
    confidence = np.asarray(
        [detection.confidence for detection in detections],
        dtype=np.float32,
    )
    class_id = np.zeros(len(detections), dtype=np.int32)
    return sv.Detections(
        xyxy=xyxy,
        confidence=confidence,
        class_id=class_id,
    )


def _to_tracked_people(detections: sv.Detections) -> list[TrackedPerson]:
    if detections.tracker_id is None or len(detections) == 0:
        return []

    tracked_people: list[TrackedPerson] = []
    for index in range(len(detections)):
        tracker_id = int(detections.tracker_id[index])
        if tracker_id < 0:
            continue
        x1, y1, x2, y2 = detections.xyxy[index]
        left = int(round(float(x1)))
        top = int(round(float(y1)))
        width = int(round(float(x2 - x1)))
        height = int(round(float(y2 - y1)))
        if width <= 0 or height <= 0:
            continue
        confidence = (
            float(detections.confidence[index])
            if detections.confidence is not None
            else 0.0
        )
        tracked_people.append(
            TrackedPerson(
                track_id=str(tracker_id),
                class_name="person",
                confidence=confidence,
                left=left,
                top=top,
                width=width,
                height=height,
            ),
        )
    return tracked_people
