"""Tests for the Roboflow ByteTrack adapter used by the tracking worker."""

from __future__ import annotations

import pytest
from src.services.tracking.contracts import PersonDetection
from src.services.tracking.trackers.bytetrack import RoboflowByteTrackPersonTracker


def test_bytetrack_returns_empty_list_for_empty_frame() -> None:
    tracker = RoboflowByteTrackPersonTracker(frame_rate=5.0)

    tracked_people = tracker.update([])

    assert not tracked_people


def test_bytetrack_assigns_a_stable_track_id_for_repeated_detection() -> None:
    tracker = RoboflowByteTrackPersonTracker(
        frame_rate=5.0,
        minimum_consecutive_frames=1,
    )
    detections = [
        PersonDetection(
            left=32.0,
            top=24.0,
            width=96.0,
            height=180.0,
            confidence=0.94,
        ),
    ]

    first_frame_tracks = tracker.update(detections)
    second_frame_tracks = tracker.update(detections)
    third_frame_tracks = tracker.update(detections)

    assert not first_frame_tracks
    assert len(second_frame_tracks) == 1
    assert len(third_frame_tracks) == 1
    assert second_frame_tracks[0].track_id == third_frame_tracks[0].track_id
    assert second_frame_tracks[0].class_name == "person"
    assert second_frame_tracks[0].confidence == pytest.approx(detections[0].confidence)
