"""
ItemDetector — lightweight object detector for items near hands.
Moved from services.inference.detection.item_detector
"""
from __future__ import annotations

import numpy as np
from libs.shared.logging.logger import get_logger

log = get_logger(__name__)


class ItemDetector:
    def __init__(self, model_path: str, device: str = "cuda") -> None:
        self._model_path = model_path
        self._device = device
        self._model = None
        self._load()

    def _load(self) -> None:
        try:
            from ultralytics import YOLO
            import os
            
            # Search order
            paths_to_try = [
                self._model_path,
                os.path.join(self._model_path, "yolo26n.engine"),
                os.path.join(self._model_path, "yolo26n.pt"),
                "models/yolo26n.pt"
            ]
            
            for path in paths_to_try:
                if os.path.exists(path) and not os.path.isdir(path):
                    self._model = YOLO(path)
                    log.info("ItemDetector loaded", extra={"path": path, "device": self._device})
                    return
            
            log.warning("ItemDetector load failed: No model file found", extra={"tried": paths_to_try})
        except Exception as exc:
            log.warning("ItemDetector load failed", extra={"error": str(exc)})

    def detect(self, frame: np.ndarray) -> list[dict]:
        if self._model is None:
            return []
        try:
            results = self._model(frame, verbose=False, classes=[39, 41, 46, 47, 67, 76])
            boxes = results[0].boxes
            if boxes is None:
                return []
            return [
                {"bbox": b.xyxy[0].tolist(), "cls": int(b.cls), "conf": float(b.conf)}
                for b in boxes
            ]
        except Exception as exc:
            log.warning("Item detection error", extra={"error": str(exc)})
            return []
