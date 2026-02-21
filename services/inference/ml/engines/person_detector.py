"""
PersonDetector — wraps YOLOv8n-seg (TRT/OpenVINO/PyTorch).
Moved from services.inference.detection.person_detector
"""
from __future__ import annotations

import numpy as np
from libs.shared.logging.logger import get_logger

log = get_logger(__name__)


class PersonDetector:
    def __init__(self, model_path: str, device: str = "cuda") -> None:
        self._model_path = model_path
        self._device = device
        self._model = None
        self._load()

    def _load(self) -> None:
        try:
            from ultralytics import YOLO
            import os
            
            # Search order: 1. Exact path, 2. Path as dir with engine, 3. Path as dir with pt
            paths_to_try = [
                self._model_path,
                os.path.join(self._model_path, "yolo26n-seg.engine"),
                os.path.join(self._model_path, "yolo26n-seg.pt"),
                "models/yolo26n-seg.pt" # Last resort default
            ]
            
            for path in paths_to_try:
                if os.path.exists(path) and not os.path.isdir(path):
                    self._model = YOLO(path)
                    log.info("PersonDetector loaded", extra={"path": path, "device": self._device})
                    return
            
            log.error("PersonDetector load failed: No model file found", extra={"tried": paths_to_try})
        except Exception as exc:
            log.error("PersonDetector load failed", extra={"error": str(exc)})

    def detect(self, frame: np.ndarray) -> tuple[list, list]:
        """Returns (bboxes, masks). Falls back to empty lists on error."""
        if self._model is None:
            return [], []
        try:
            results = self._model(frame, verbose=False)
            boxes = results[0].boxes.xyxy.cpu().numpy().tolist() if results[0].boxes else []
            masks = results[0].masks.data.cpu().numpy() if results[0].masks else []
            return boxes, masks
        except Exception as exc:
            log.warning("Detection failed", extra={"error": str(exc)})
            return [], []
