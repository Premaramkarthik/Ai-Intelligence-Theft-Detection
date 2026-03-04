"""
ItemDetector — lightweight object detector using YOLO 2.6.
"""
from __future__ import annotations

import os
import numpy as np
from ultralytics import YOLO
from shared.logging.logger import get_logger

log = get_logger(__name__)


class ItemDetector:
    def __init__(self, model_path: str | None = None, device: str = "cuda") -> None:
        self._model_path = model_path
        self._device = device
        self._model = None
        self._load()

    def _load(self) -> None:
        """
        Loads the YOLO 2.6 detection model.
        Order:
        1. Provided model_path (if any)
        2. backend/models/yolo26n.pt
        3. Fallback to Ultralytics API (auto-download)
        """
        try:
            # Search order
            paths_to_try: list[str] = []
            if self._model_path:
                paths_to_try.append(str(self._model_path))
            
            # Default local path
            paths_to_try.append("models/yolo26n.pt")
            
            for path in paths_to_try:
                if os.path.exists(path) and not os.path.isdir(path):
                    self._model = YOLO(path)
                    log.info("ItemDetector loaded from local file", extra={"path": path, "device": self._device})
                    return
            
            # Fallback to Ultralytics API
            log.info("ItemDetector: Local model not found, falling back to Ultralytics API")
            self._model = YOLO("yolo26n.pt")
            log.info("ItemDetector loaded via Ultralytics API", extra={"model": "yolo26n.pt"})
                
        except Exception as exc:
            log.warning("ItemDetector load failed", extra={"error": str(exc)})

    def detect(self, frame: np.ndarray) -> list[dict]:
        if self._model is None:
            return []
        try:
            # Common COCO item classes for watch: bottle, backpack, handbag, suitcase, sports ball, etc.
            # Classes are COCO indices: bottle=39, backpack=24, handbag=26, suitcase=28
            # The previous code used [39, 41, 46, 47, 67, 76]
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
