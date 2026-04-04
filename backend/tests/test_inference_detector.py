"""Tests for the Roboflow Inference detector used by tracking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest
from src.services.tracking.detectors.inference_detector import InferencePersonDetector


@dataclass(slots=True)
class _FakePrediction:
    x: float
    y: float
    width: float
    height: float
    confidence: float
    class_name: str


@dataclass(slots=True)
class _FakeResult:
    predictions: list[_FakePrediction]


class _FakeInferenceModel:
    def __init__(self, results: list[_FakeResult]) -> None:
        self._results = results
        self.calls: list[dict[str, Any]] = []

    def infer(self, image: np.ndarray, **kwargs: Any) -> list[_FakeResult]:
        self.calls.append(
            {
                "shape": image.shape,
                "kwargs": kwargs,
            },
        )
        return self._results


def test_inference_detector_requests_person_filter_and_maps_boxes() -> None:
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    fake_model = _FakeInferenceModel(
        [
            _FakeResult(
                predictions=[
                    _FakePrediction(
                        x=90.0,
                        y=120.0,
                        width=80.0,
                        height=160.0,
                        confidence=0.93,
                        class_name="person",
                    ),
                    _FakePrediction(
                        x=200.0,
                        y=100.0,
                        width=50.0,
                        height=70.0,
                        confidence=0.87,
                        class_name="dog",
                    ),
                ],
            ),
        ],
    )
    detector = InferencePersonDetector(
        model_id="rfdetr-medium",
        confidence_threshold=0.4,
        iou_threshold=0.3,
        model=fake_model,
    )

    detections = detector.detect(frame)

    assert len(fake_model.calls) == 1
    assert fake_model.calls[0]["shape"] == frame.shape
    assert fake_model.calls[0]["kwargs"] == {
        "confidence": 0.4,
        "iou_threshold": 0.3,
        "class_filter": ["person"],
    }
    assert len(detections) == 1
    assert detections[0].left == pytest.approx(50.0)
    assert detections[0].top == pytest.approx(40.0)
    assert detections[0].width == pytest.approx(80.0)
    assert detections[0].height == pytest.approx(160.0)
    assert detections[0].confidence == pytest.approx(0.93)
    assert detections[0].class_name == "person"
