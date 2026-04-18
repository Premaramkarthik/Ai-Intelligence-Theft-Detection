from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from src.opencv_pipeline.contracts import ProcessedFrame, TrackedObject
from src.opencv_pipeline.identity.service import IdentityAssignmentService
from src.services.tracking.identity.milvus_store import IdentityMatch


class FakeIdentityStore:
    def __init__(self, matches: list[IdentityMatch]) -> None:
        self._matches = matches
        self.ensure_ready_called = False
        self.closed = False

    def ensure_ready(self) -> None:
        self.ensure_ready_called = True

    async def batch_resolve(self, requests):
        return self._matches[: len(requests)]

    def close(self) -> None:
        self.closed = True


def _processed_frame() -> ProcessedFrame:
    frame = np.zeros((16, 16, 3), dtype=np.uint8)
    timestamp = datetime.now(timezone.utc)
    return ProcessedFrame(
        packet=type(
            "Packet",
            (),
            {
                "camera_id": "cam_1",
                "stream_name": "front_gate",
                "sequence_number": 1,
                "captured_at": timestamp,
                "monotonic_ns": 1,
            },
        )(),
        calibration=None,
        raw_bgr=frame,
        working_bgr=frame,
        rgb=frame,
        normalized_rgb=frame.astype(np.float32),
        gray=np.zeros((16, 16), dtype=np.uint8),
        low_light=False,
        world_reference_frame=None,
    )


def _track() -> TrackedObject:
    track = TrackedObject(
        camera_id="cam_1",
        stream_name="front_gate",
        track_id="track_1",
        left=1,
        top=2,
        width=3,
        height=4,
        confidence=0.9,
    )
    track.embedding = np.ones((1280,), dtype=np.float32)
    return track


async def test_identity_assignment_service_emits_create_and_expire_events() -> None:
    store = FakeIdentityStore(
        [IdentityMatch(identity_id="person_1", matched_existing=False, similarity=0.92)]
    )
    service = IdentityAssignmentService(store, identity_ttl_seconds=1.0)
    service.ensure_ready()

    events, _latency_ms = await service.assign([(_processed_frame(), [_track()])])

    assert store.ensure_ready_called is True
    assert len(events) == 1
    assert events[0].event_type.value == "identity.created"
    expired = service.expire_stale(reference_time=datetime.now(timezone.utc) + timedelta(seconds=2))
    assert len(expired) == 1
    assert expired[0].event_type.value == "identity.expired"


async def test_identity_assignment_service_marks_merged_identity_when_match_changes() -> None:
    store = FakeIdentityStore(
        [IdentityMatch(identity_id="person_a", matched_existing=False, similarity=0.91)]
    )
    service = IdentityAssignmentService(store, identity_ttl_seconds=30.0)
    track = _track()
    await service.assign([(_processed_frame(), [track])])

    store._matches = [IdentityMatch(identity_id="person_b", matched_existing=True, similarity=0.95)]
    second_track = _track()
    events, _latency_ms = await service.assign([(_processed_frame(), [second_track])])

    assert any(event.event_type.value == "identity.merged" for event in events)


async def test_identity_assignment_service_remove_camera_expires_only_that_camera() -> None:
    store = FakeIdentityStore(
        [IdentityMatch(identity_id="person_a", matched_existing=False, similarity=0.91)]
    )
    service = IdentityAssignmentService(store, identity_ttl_seconds=30.0)
    await service.assign([(_processed_frame(), [_track()])])

    expired = service.remove_camera("cam_1")

    assert len(expired) == 1
    assert expired[0].event_type.value == "identity.expired"
    assert service.remove_camera("cam_1") == []
