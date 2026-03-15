from unittest.mock import AsyncMock

import pytest

from services.inference.ml.engines.object_detector import ObjectDetector
from services.inference.ml.pipeline import InferencePipeline
from services.inference.services.interaction import ItemInteractionDetector
from services.inference.services.reid_service import ReIDService


def test_per_camera_runtime_state_isolated():
    pipeline = InferencePipeline()

    cam_a = pipeline._new_state()
    cam_b = pipeline._new_state()

    cam_a.frame_count = 11
    cam_a.skip_n = 5
    cam_a.current_incident = None
    cam_a.buffer.push(__import__("numpy").zeros((2, 2, 3), dtype="uint8"))
    cam_a.interaction.update(
        [{"id": "track-a", "bbox": [0, 0, 100, 200]}],
        [{"bbox": [20, 140, 60, 190], "label": "item", "conf": 0.9}],
    )

    assert cam_b.frame_count == 0
    assert cam_b.skip_n != cam_a.skip_n
    assert len(cam_a.buffer) == 1
    assert len(cam_b.buffer) == 0
    assert cam_a.interaction is not cam_b.interaction


def test_interaction_requires_real_item_proximity():
    detector = ItemInteractionDetector(hand_dist_px=40, interaction_frames=2)
    person = {"id": "track-a", "bbox": [0, 0, 100, 200]}
    near_item = {"bbox": [20, 145, 60, 190], "label": "item", "conf": 0.9}
    far_item = {"bbox": [300, 10, 360, 60], "label": "item", "conf": 0.9}

    detector.update([person], [])
    assert detector.should_classify() is False
    assert detector._states["track-a"] == 0

    detector.update([person], [far_item])
    assert detector.should_classify() is False
    assert detector._states["track-a"] == 0

    detector.update([person], [near_item])
    assert detector.should_classify() is False
    assert detector._states["track-a"] == 1

    detector.update([person], [near_item])
    assert detector.should_classify() is True
    assert detector._states["track-a"] == 0


def test_detector_tracker_models_are_isolated_per_camera():
    detector = ObjectDetector.__new__(ObjectDetector)
    detector._tracker_models = {}
    detector._model_path = "unused"

    created = []

    def fake_load_model(_path: str):
        model = object()
        created.append(model)
        return model

    detector._load_model = fake_load_model  # type: ignore[method-assign]

    cam_a_first = detector._tracker_model("cam-a")
    cam_a_second = detector._tracker_model("cam-a")
    cam_b_first = detector._tracker_model("cam-b")

    assert cam_a_first is cam_a_second
    assert cam_a_first is not cam_b_first
    assert len(created) == 2


@pytest.mark.asyncio
async def test_load_camera_config_preserves_interaction_state():
    pipeline = InferencePipeline()
    state = pipeline._new_state()
    state.interaction.update(
        [{"id": "track-a", "bbox": [0, 0, 100, 200]}],
        [{"bbox": [20, 145, 60, 190], "label": "item", "conf": 0.9}],
    )
    original_interaction = state.interaction

    redis = AsyncMock()
    redis.hgetall.return_value = {
        "enabled": "true",
        "confidence_threshold": "0.6",
        "hand_dist_px": str(original_interaction.hand_dist_px),
        "interaction_frames": str(original_interaction.interaction_frames),
    }

    config = await pipeline._load_camera_config("cam-a", redis, state)

    assert config.hand_dist_px == original_interaction.hand_dist_px
    assert config.interaction_frames == original_interaction.interaction_frames
    assert state.interaction is original_interaction
    assert state.interaction._states["track-a"] == 1


@pytest.mark.asyncio
async def test_load_camera_config_reconfigures_detector_without_replacing_it():
    pipeline = InferencePipeline()
    state = pipeline._new_state()
    original_interaction = state.interaction

    redis = AsyncMock()
    redis.hgetall.return_value = {
        "enabled": "true",
        "confidence_threshold": "0.6",
        "hand_dist_px": "120",
        "interaction_frames": "7",
    }

    config = await pipeline._load_camera_config("cam-a", redis, state)

    assert config.hand_dist_px == 120
    assert config.interaction_frames == 7
    assert state.interaction is original_interaction
    assert state.interaction.hand_dist_px == 120
    assert state.interaction.interaction_frames == 7


def test_reid_disables_honestly_when_model_unavailable():
    service = ReIDService(AsyncMock())
    service.available = False
    service.model = None

    assert service.extract_features(__import__("numpy").zeros((32, 32, 3), dtype="uint8")) is None
