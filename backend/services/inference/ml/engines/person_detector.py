"""
PersonDetector — wraps YOLO 2.6 segmentation models.
"""
from __future__ import annotations

import os
import numpy as np
from ultralytics import YOLO
from shared.logging.logger import get_logger

log = get_logger(__name__)


class PersonDetector:
    def __init__(self, model_path: str | None = None, device: str = "cuda") -> None:
        self._model_path = model_path
        self._device = device
        self._model = None
        self._load()

    def _load(self) -> None:
        """
        Loads the YOLO 2.6 segmentation model.
        Order: 
        1. Provided model_path (if any)
        2. backend/models/yolo26n-seg.pt
        3. Fallback to Ultralytics API (auto-download)
        """
        try:
            # Search order
            paths_to_try: list[str] = []
            if self._model_path:
                paths_to_try.append(str(self._model_path))
            
            # Default local path
            paths_to_try.append("models/yolo26n-seg.pt")
            
            for path in paths_to_try:
                if os.path.exists(path) and not os.path.isdir(path):
                    self._model = YOLO(path)
                    log.info("PersonDetector loaded from local file", extra={"path": path, "device": self._device})
                    return
            
            # Fallback to Ultralytics API
            log.info("PersonDetector: Local model not found, falling back to Ultralytics API")
            self._model = YOLO("yolo26n-seg.pt")
            log.info("PersonDetector loaded via Ultralytics API", extra={"model": "yolo26n-seg.pt"})
                
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
