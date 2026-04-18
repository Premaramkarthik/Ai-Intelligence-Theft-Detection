"""Batched YOLO detection stage for person/object detection."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter_ns
from typing import Sequence

import numpy as np
import torch
from ultralytics import YOLO

from src.core.logger.logger import get_logger
from src.opencv_pipeline.contracts import Detection


class YOLOBatchDetector:
    """Run batched YOLO inference over one or more synchronized frames."""

    def __init__(
        self,
        model_path: Path,
        *,
        confidence_threshold: float,
        class_ids: Sequence[int] | None = None,
        max_batch_size: int = 8,
        device: str | int | None = None,
    ) -> None:
        self._model_path = model_path
        self._model = YOLO(str(model_path))
        self._confidence_threshold = confidence_threshold
        self._class_ids = list(class_ids or [])
        self._max_batch_size = max(1, max_batch_size)
        self._device = device if device is not None else (0 if torch.cuda.is_available() else "cpu")
        self._logger = get_logger(__name__)
        self._logger.info(
            "Person detector initialised.",
            extra={
                "structured": {
                    "event": "person_detection.initialized",
                    "model_path": str(model_path),
                    "confidence_threshold": confidence_threshold,
                    "class_ids": list(self._class_ids),
                    "max_batch_size": self._max_batch_size,
                    "device": str(self._device),
                }
            },
        )

    def detect_batch(self, frames: Sequence[np.ndarray]) -> list[list[Detection]]:
        """Run batched detection and return per-frame detections in LTWH format."""

        started_at = perf_counter_ns()
        results: list[list[Detection]] = []
        try:
            for batch_start in range(0, len(frames), self._max_batch_size):
                batch = list(frames[batch_start : batch_start + self._max_batch_size])
                if not batch:
                    continue
                batch_results = self._model.predict(
                    source=batch,
                    conf=self._confidence_threshold,
                    classes=self._class_ids or None,
                    device=self._device,
                    verbose=False,
                    batch=len(batch),
                )
                results.extend(_to_detections(result) for result in batch_results)
        except Exception:
            self._logger.exception(
                "Person detection batch failed.",
                extra={
                    "structured": {
                        "event": "person_detection.batch_failed",
                        "frame_count": len(frames),
                        "max_batch_size": self._max_batch_size,
                        "device": str(self._device),
                        "model_path": str(self._model_path),
                    }
                },
            )
            raise
        self._logger.debug(
            "Person detection batch completed.",
            extra={
                "structured": {
                    "event": "person_detection.batch_completed",
                    "frame_count": len(frames),
                    "result_frame_count": len(results),
                    "total_detections": sum(len(batch) for batch in results),
                    "latency_ms": round((perf_counter_ns() - started_at) / 1_000_000.0, 3),
                    "device": str(self._device),
                    "model_path": str(self._model_path),
                }
            },
        )
        return results


def _to_detections(result: object) -> list[Detection]:
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []

    xyxy = boxes.xyxy.cpu().numpy()
    confidences = boxes.conf.cpu().numpy()
    class_ids = boxes.cls.cpu().numpy() if boxes.cls is not None else np.zeros(len(xyxy))
    names = getattr(result, "names", {}) or {}

    detections: list[Detection] = []
    for index in range(len(xyxy)):
        x1, y1, x2, y2 = xyxy[index]
        left = int(round(float(x1)))
        top = int(round(float(y1)))
        width = int(round(float(x2 - x1)))
        height = int(round(float(y2 - y1)))
        if width <= 0 or height <= 0:
            continue
        class_id = int(class_ids[index])
        detections.append(
            Detection(
                left=left,
                top=top,
                width=width,
                height=height,
                confidence=float(confidences[index]),
                class_id=class_id,
                class_name=str(names.get(class_id, class_id)),
            )
        )
    return detections

