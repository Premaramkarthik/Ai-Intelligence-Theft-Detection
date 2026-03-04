"""
ObjectDetector — unified YOLO segmentation model for persons + items.

Single forward pass splits results:
  - class 0 (person) → bboxes, masks, track IDs
  - class != 0        → item dicts with bbox, cls, label, conf

Supports TensorRT (.engine) for 2-6x inference speedup.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np
from ultralytics import YOLO
from shared.logging.logger import get_logger

log = get_logger(__name__)

PERSON_CLS = 0
MODEL_CANDIDATES = [
    "models/yolo26n-seg.engine",  # TensorRT (preferred)
    "models/yolo26n-seg.pt",      # PyTorch fallback
]


@dataclass
class DetectionResult:
    person_boxes: list = field(default_factory=list)
    person_masks: list = field(default_factory=list)
    track_ids: list = field(default_factory=list)
    items: list[dict] = field(default_factory=list)


class ObjectDetector:
    def __init__(self, model_path: str | None = None, device: str = "cuda") -> None:
        self._device = device
        self._model: YOLO | None = None

        paths = []
        if model_path:
            paths.append(str(model_path))
        paths.extend(MODEL_CANDIDATES)

        for p in paths:
            if os.path.exists(p) and not os.path.isdir(p):
                self._model = YOLO(p)
                log.info("ObjectDetector loaded", extra={"path": p, "device": device})
                return

        self._model = YOLO("yolo26n-seg.pt")
        log.info("ObjectDetector loaded via Ultralytics hub")

    def warmup(self, imgsz: tuple[int, int] = (640, 640)) -> None:
        """Run 3 dummy passes to warm up GPU kernels and TensorRT engine."""
        if self._model is None:
            return
        dummy = np.zeros((*imgsz, 3), dtype=np.uint8)
        for _ in range(3):
            self._model.predict(dummy, verbose=False)
        log.info("ObjectDetector warmup complete")

    def detect_and_track(
        self, frame: np.ndarray, tracker_id: str = "default"
    ) -> DetectionResult:
        """Single forward pass: track persons + detect items.

        Args:
            frame: BGR image (H, W, 3).
            tracker_id: unique ID per camera to isolate tracker state.
        """
        if self._model is None:
            return DetectionResult()
        try:
            results = self._model.track(
                frame, persist=True, verbose=False, tracker=tracker_id
            )
            res = results[0]

            result = DetectionResult()
            if not res.boxes:
                return result

            classes = res.boxes.cls.cpu().numpy().astype(int)
            boxes = res.boxes.xyxy.cpu().numpy()
            confs = res.boxes.conf.cpu().numpy()
            ids = (
                res.boxes.id.cpu().numpy().astype(int)
                if res.boxes.id is not None
                else np.array([])
            )
            masks = res.masks.data.cpu().numpy() if res.masks is not None else []

            for i, cls in enumerate(classes):
                bbox = boxes[i].tolist()
                if cls == PERSON_CLS:
                    result.person_boxes.append(bbox)
                    if len(masks) > 0 and i < len(masks):
                        result.person_masks.append(masks[i])
                    result.track_ids.append(
                        int(ids[i]) if i < len(ids) else i + 1
                    )
                else:
                    result.items.append({
                        "bbox": bbox,
                        "cls": int(cls),
                        "label": self._model.names[int(cls)],
                        "conf": float(confs[i]),
                    })

            return result
        except Exception as exc:
            log.warning("Detection failed", extra={"error": str(exc)})
            return DetectionResult()
