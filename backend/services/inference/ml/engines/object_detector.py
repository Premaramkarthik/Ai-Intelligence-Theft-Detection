"""
Object detector wrapper for TensorRT or ONNX detector models.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np
from shared.logging.logger import get_logger
from ultralytics import YOLO

log = get_logger(__name__)

PERSON_CLS = 0
DETECTOR_ENGINE_FILENAME = "yolo26n.engine"
DETECTOR_ONNX_FILENAME = "yolo26n.onnx"


@dataclass
class DetectionResult:
    person_boxes: list = field(default_factory=list)
    person_masks: list = field(default_factory=list)
    track_ids: list = field(default_factory=list)
    items: list[dict] = field(default_factory=list)


class ObjectDetector:
    def __init__(self, model_path: str, device: str = "cuda") -> None:
        self._device = device
        self._model_path = model_path
        self._is_onnx = model_path.endswith(".onnx")
        self._base_model = self._load_model(model_path)
        self._tracker_models: dict[str, YOLO] = {}

    def _load_model(self, model_path: str) -> YOLO:
        if os.path.isdir(model_path) or not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Required detector model is missing: {model_path}. "
                f"Expected `{DETECTOR_ENGINE_FILENAME}` or `{DETECTOR_ONNX_FILENAME}`."
            )
        if not model_path.endswith((".engine", ".onnx")):
            raise ValueError(f"Detector must use a TensorRT engine or ONNX model, got: {model_path}")

        model = YOLO(model_path)
        log.info("ObjectDetector loaded", extra={"path": model_path, "device": self._device})
        return model

    def _predict_kwargs(self) -> dict:
        kwargs: dict[str, object] = {}
        if self._device in {"cpu", "cuda"}:
            kwargs["device"] = self._device
        if self._is_onnx and self._device == "cpu":
            # Use OpenCV DNN for local CPU fallback when TensorRT/CUDA is unavailable.
            kwargs["dnn"] = True
            kwargs["agnostic_nms"] = True
            kwargs["imgsz"] = 640
            kwargs["conf"] = 0.25
            kwargs["iou"] = 0.45
        else:
            kwargs["agnostic_nms"] = True
        return kwargs

    def _tracker_model(self, tracker_id: str) -> YOLO:
        if tracker_id not in self._tracker_models:
            self._tracker_models[tracker_id] = self._load_model(self._model_path)
            log.info("Tracker model isolated", extra={"tracker_id": tracker_id})
        return self._tracker_models[tracker_id]

    def warmup(self, imgsz: tuple[int, int] = (640, 640)) -> None:
        dummy = np.zeros((*imgsz, 3), dtype=np.uint8)
        for _ in range(3):
            self._base_model.predict(dummy, verbose=False, **self._predict_kwargs())
        log.info("ObjectDetector warmup complete")

    def detect_and_track(self, frame: np.ndarray, tracker_id: str = "default") -> DetectionResult:
        try:
            model = self._tracker_model(tracker_id)
            results = model.track(
                frame,
                persist=True,
                verbose=False,
                **self._predict_kwargs(),
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
                    result.track_ids.append(int(ids[i]) if i < len(ids) else i + 1)
                    continue

                result.items.append(
                    {
                        "bbox": bbox,
                        "cls": int(cls),
                        "label": model.names[int(cls)],
                        "conf": float(confs[i]),
                    }
                )

            return result
        except Exception as exc:
            log.warning("Detection failed", extra={"error": str(exc), "tracker_id": tracker_id})
            return DetectionResult()
