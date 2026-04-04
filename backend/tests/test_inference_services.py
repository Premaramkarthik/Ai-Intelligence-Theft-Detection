"""Focused tests for temporal inference services."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from src.services.inference.batch_builder import BatchBuilder
from src.services.inference.contracts import (
    InferenceAlertEvent,
    ModelPrediction,
)
from src.services.inference.decision_engine import DecisionEngine
from src.services.inference.repository import InferenceEventRepository
from src.services.inference.track_state_manager import TrackStateManager


def test_track_state_manager_gates_sequences_by_stride_and_prunes_expired() -> None:
    manager = TrackStateManager(
        sequence_length=4,
        stride_frames=2,
        lost_track_ttl_seconds=2.0,
        expire_track_ttl_seconds=10.0,
    )
    seen_at = datetime.now(timezone.utc)
    crop = np.zeros((32, 32, 3), dtype=np.uint8)
    pose = np.zeros((17, 3), dtype=np.float32)

    first_ready = manager.ingest(
        camera_id="cam_1",
        track_id="track_1",
        persistent_id="person_1",
        model_name="stgcn_pose",
        left=10,
        top=12,
        width=40,
        height=60,
        crop_frame=crop,
        pose_frame=pose,
        seen_at=seen_at,
    )
    second_ready = manager.ingest(
        camera_id="cam_1",
        track_id="track_1",
        persistent_id="person_1",
        model_name="stgcn_pose",
        left=10,
        top=12,
        width=40,
        height=60,
        crop_frame=crop,
        pose_frame=pose,
        seen_at=seen_at + timedelta(milliseconds=150),
    )

    assert first_ready is None
    assert second_ready is not None
    assert second_ready.pose_sequence.shape == (2, 17, 3)
    assert manager.active_track_count("cam_1", seen_at + timedelta(seconds=1)) == 1
    assert manager.active_track_count("cam_1", seen_at + timedelta(seconds=3)) == 0

    manager.prune_expired(seen_at + timedelta(seconds=11))

    assert manager.active_cameras() == []


def test_batch_builder_front_pads_short_pose_sequences() -> None:
    builder = BatchBuilder(
        sequence_length=4,
        pose_keypoint_count=3,
        max_batch_size=16,
    )
    pose_sequence = np.asarray(
        [
            [[1.0, 0.1, 0.9], [2.0, 0.2, 0.8], [3.0, 0.3, 0.7]],
            [[4.0, 0.4, 0.6], [5.0, 0.5, 0.5], [6.0, 0.6, 0.4]],
        ],
        dtype=np.float32,
    )

    from src.services.inference.contracts import ReadyTrackSequence

    batches = builder.build_pose_batches(
        [
            ReadyTrackSequence(
                camera_id="cam_1",
                track_id="track_1",
                persistent_id=None,
                model_name="stgcn_pose",
                left=1,
                top=2,
                width=3,
                height=4,
                pose_sequence=pose_sequence,
                crop_sequence=None,
            ),
        ],
    )

    assert len(batches) == 1
    assert batches[0].inputs.shape == (1, 3, 4, 3, 1)
    assert np.allclose(batches[0].inputs[0, :, 0, :, 0], batches[0].inputs[0, :, 1, :, 0])


def test_decision_engine_requires_hysteresis_for_entry_and_clear() -> None:
    engine = DecisionEngine(
        alpha=0.35,
        alert_threshold=0.7,
        clear_threshold=0.35,
        enter_consecutive_count=3,
        clear_consecutive_count=5,
        normal_label="normal",
    )

    def build_prediction(shoplifting_score: float) -> ModelPrediction:
        return ModelPrediction(
            camera_id="cam_1",
            track_id="track_1",
            persistent_id=None,
            model_name="stgcn_pose",
            left=5,
            top=6,
            width=7,
            height=8,
            scores={
                "normal": 1.0 - shoplifting_score,
                "shoplifting": shoplifting_score,
            },
            predicted_label="shoplifting" if shoplifting_score >= 0.5 else "normal",
            predicted_confidence=shoplifting_score,
        )

    first = engine.evaluate(build_prediction(0.82))
    second = engine.evaluate(build_prediction(0.84))
    third = engine.evaluate(build_prediction(0.87))

    assert first.label == "normal"
    assert second.label == "normal"
    assert third.label == "shoplifting"
    assert third.transition_emitted is True

    clears = [engine.evaluate(build_prediction(0.05)) for _ in range(8)]

    assert any(result.label == "normal" for result in clears[4:])
    assert any(result.transition_emitted for result in clears[4:])


@pytest.mark.asyncio
async def test_inference_event_repository_persists_and_fetches_latest_alert() -> None:
    class FakeDatabase:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...]]] = []

        async def fetchrow_file(self, relative_path: str, *params: object):
            self.calls.append((relative_path, params))
            if relative_path == "inference/insert_inference_event.sql":
                return {
                    "id": params[0],
                    "camera_id": params[1],
                    "track_id": params[2],
                    "persistent_id": params[3],
                    "label": params[4],
                    "confidence": params[5],
                    "left": params[6],
                    "top": params[7],
                    "width": params[8],
                    "height": params[9],
                    "model_name": params[10],
                    "created_at": params[11],
                }
            if relative_path == "inference/get_latest_non_normal_event.sql":
                return {
                    "camera_id": params[0],
                    "track_id": "track_1",
                    "persistent_id": "person_1",
                    "label": "shoplifting",
                    "confidence": 0.91,
                    "left": 10,
                    "top": 20,
                    "width": 30,
                    "height": 40,
                    "model_name": "stgcn_pose",
                    "created_at": datetime.now(timezone.utc),
                }
            return None

    repository = InferenceEventRepository(FakeDatabase())
    event = InferenceAlertEvent(
        camera_id="cam_1",
        track_id="track_1",
        persistent_id="person_1",
        label="shoplifting",
        confidence=0.91,
        left=10,
        top=20,
        width=30,
        height=40,
        timestamp=datetime.now(timezone.utc),
        model_name="stgcn_pose",
    )

    record = await repository.insert(event)
    latest = await repository.fetch_latest_non_normal("cam_1")

    assert record.camera_id == "cam_1"
    assert record.label == "shoplifting"
    assert latest is not None
    assert latest.camera_id == "cam_1"
    assert latest.label == "shoplifting"
