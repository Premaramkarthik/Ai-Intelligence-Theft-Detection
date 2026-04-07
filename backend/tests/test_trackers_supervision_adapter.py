"""Tests for RoboflowByteTrackPersonTracker: stability fields, empty detections, field types."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest
import supervision as sv

from src.services.tracking.contracts import PersonDetection
from src.services.tracking.trackers.bytetrack import (
    RoboflowByteTrackPersonTracker,
    TrackedPerson,
)


def _make_tracker() -> RoboflowByteTrackPersonTracker:
    return RoboflowByteTrackPersonTracker(frame_rate=5.0, minimum_consecutive_frames=1)


def _sv_detections(
    *,
    tracker_id: int = 7,
    x1: float = 10.0,
    y1: float = 20.0,
    x2: float = 110.0,
    y2: float = 220.0,
    confidence: float = 0.92,
    age: int = 5,
    hit_streak: int = 3,
    frames_since_update: int = 0,
) -> sv.Detections:
    return sv.Detections(
        xyxy=np.array([[x1, y1, x2, y2]], dtype=np.float32),
        confidence=np.array([confidence], dtype=np.float32),
        class_id=np.array([0], dtype=np.int32),
        tracker_id=np.array([tracker_id], dtype=np.int64),
        data={
            "age": np.array([age], dtype=np.int32),
            "hit_streak": np.array([hit_streak], dtype=np.int32),
            "frames_since_update": np.array([frames_since_update], dtype=np.int32),
        },
    )


# ---------------------------------------------------------------------------
# Stability fields round-trip through the adapter
# ---------------------------------------------------------------------------


def test_stability_fields_survive_adapter_round_trip() -> None:
    tracker = _make_tracker()
    tracker._tracker = MagicMock()
    tracker._tracker.update.return_value = _sv_detections(age=5, hit_streak=3, frames_since_update=1)

    results = tracker.update([PersonDetection(left=10, top=20, width=100, height=200, confidence=0.9)])

    assert len(results) == 1
    person = results[0]
    assert person.age_frames == 5
    assert person.consecutive_hits == 3
    assert person.frames_since_update == 1


def test_stability_fields_default_to_zero_when_data_absent() -> None:
    tracker = _make_tracker()
    tracker._tracker = MagicMock()

    # sv.Detections without the stability data keys.
    tracker._tracker.update.return_value = sv.Detections(
        xyxy=np.array([[10.0, 20.0, 110.0, 220.0]], dtype=np.float32),
        confidence=np.array([0.88], dtype=np.float32),
        class_id=np.array([0], dtype=np.int32),
        tracker_id=np.array([1], dtype=np.int64),
        data={},
    )

    results = tracker.update([PersonDetection(left=10, top=20, width=100, height=200, confidence=0.88)])

    assert len(results) == 1
    assert results[0].age_frames == 0
    assert results[0].consecutive_hits == 0
    assert results[0].frames_since_update == 0


# ---------------------------------------------------------------------------
# Empty detections → empty list
# ---------------------------------------------------------------------------


def test_update_with_empty_detections_returns_empty_list() -> None:
    tracker = _make_tracker()
    tracker._tracker = MagicMock()
    tracker._tracker.update.return_value = sv.Detections.empty()

    result = tracker.update([])

    assert result == []


def test_update_with_no_tracker_ids_returns_empty_list() -> None:
    tracker = _make_tracker()
    tracker._tracker = MagicMock()

    detections = sv.Detections(
        xyxy=np.empty((0, 4), dtype=np.float32),
        confidence=np.empty(0, dtype=np.float32),
        class_id=np.empty(0, dtype=np.int32),
    )
    detections.tracker_id = None
    tracker._tracker.update.return_value = detections

    result = tracker.update([PersonDetection(left=10, top=20, width=100, height=200, confidence=0.9)])
    assert result == []


# ---------------------------------------------------------------------------
# Field types: track_id is str, bbox fields are ints
# ---------------------------------------------------------------------------


def test_track_id_is_string() -> None:
    tracker = _make_tracker()
    tracker._tracker = MagicMock()
    tracker._tracker.update.return_value = _sv_detections(tracker_id=42)

    results = tracker.update([PersonDetection(left=10, top=20, width=100, height=200, confidence=0.9)])

    assert isinstance(results[0].track_id, str)
    assert results[0].track_id == "42"


def test_bbox_fields_are_ints() -> None:
    tracker = _make_tracker()
    tracker._tracker = MagicMock()
    tracker._tracker.update.return_value = _sv_detections(
        x1=10.6, y1=20.4, x2=110.5, y2=220.7
    )

    results = tracker.update([PersonDetection(left=10, top=20, width=100, height=200, confidence=0.9)])

    person = results[0]
    assert isinstance(person.left, int)
    assert isinstance(person.top, int)
    assert isinstance(person.width, int)
    assert isinstance(person.height, int)


def test_class_name_is_always_person() -> None:
    tracker = _make_tracker()
    tracker._tracker = MagicMock()
    tracker._tracker.update.return_value = _sv_detections()

    results = tracker.update([PersonDetection(left=10, top=20, width=100, height=200, confidence=0.9)])

    assert results[0].class_name == "person"
