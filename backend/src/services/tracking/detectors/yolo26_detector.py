from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(slots=True, frozen=True)
class PersonDetection:
    """A single person detection in left-top-width-height format."""

    left: float
    top: float
    width: float
    height: float
    confidence: float
    class_name: str = "person"


class Yolo26PersonDetector:
    """Run lightweight person detection with the existing YOLO26 ONNX asset."""

    def __init__(
        self,
        model_path: str | Path,
        *,
        input_size: int = 640,
        confidence_threshold: float = 0.35,
        iou_threshold: float = 0.45,
        person_class_id: int = 0,
    ) -> None:
        self._model_path = Path(model_path)
        self._input_size = input_size
        self._confidence_threshold = confidence_threshold
        self._iou_threshold = iou_threshold
        self._person_class_id = person_class_id
        self._net = cv2.dnn.readNetFromONNX(str(self._model_path))

    def detect(self, frame: np.ndarray) -> list[PersonDetection]:
        """Detect persons in a BGR frame."""

        blob, resize_scale, pad_x, pad_y = _build_letterboxed_blob(
            frame,
            self._input_size,
        )
        self._net.setInput(blob)
        output = self._net.forward()
        return self._decode_output(
            output,
            frame_shape=frame.shape[:2],
            resize_scale=resize_scale,
            pad_x=pad_x,
            pad_y=pad_y,
        )

    def _decode_output(
        self,
        output: np.ndarray,
        *,
        frame_shape: tuple[int, int],
        resize_scale: float,
        pad_x: float,
        pad_y: float,
    ) -> list[PersonDetection]:
        if output.ndim == 3 and output.shape[-1] == 6:
            return self._decode_end_to_end_output(
                output[0],
                frame_shape=frame_shape,
                resize_scale=resize_scale,
                pad_x=pad_x,
                pad_y=pad_y,
            )

        candidates = output[0]
        if candidates.ndim == 2 and candidates.shape[0] < candidates.shape[1]:
            candidates = candidates.T

        boxes: list[list[int]] = []
        confidences: list[float] = []
        detections: list[PersonDetection] = []
        for row in candidates:
            if row.shape[0] < 6:
                continue
            objectness = float(row[4])
            class_scores = row[5:]
            class_id = int(np.argmax(class_scores)) if class_scores.size else 0
            confidence = objectness * (
                float(class_scores[class_id]) if class_scores.size else 1.0
            )
            if confidence < self._confidence_threshold or class_id != self._person_class_id:
                continue
            left, top, width, height = _restore_cxcywh_box(
                center_x=float(row[0]),
                center_y=float(row[1]),
                width=float(row[2]),
                height=float(row[3]),
                frame_shape=frame_shape,
                resize_scale=resize_scale,
                pad_x=pad_x,
                pad_y=pad_y,
            )
            boxes.append([left, top, width, height])
            confidences.append(confidence)
            detections.append(
                PersonDetection(
                    left=left,
                    top=top,
                    width=width,
                    height=height,
                    confidence=confidence,
                ),
            )
        keep_indices = cv2.dnn.NMSBoxes(
            boxes,
            confidences,
            score_threshold=self._confidence_threshold,
            nms_threshold=self._iou_threshold,
        )
        return _select_indices(detections, keep_indices)

    def _decode_end_to_end_output(
        self,
        detections: np.ndarray,
        *,
        frame_shape: tuple[int, int],
        resize_scale: float,
        pad_x: float,
        pad_y: float,
    ) -> list[PersonDetection]:
        parsed_detections: list[PersonDetection] = []
        for row in detections:
            if row.shape[0] != 6:
                continue
            confidence = float(row[4])
            class_id = int(round(float(row[5])))
            if confidence < self._confidence_threshold or class_id != self._person_class_id:
                continue
            left, top, width, height = _restore_xyxy_box(
                left=float(row[0]),
                top=float(row[1]),
                right=float(row[2]),
                bottom=float(row[3]),
                frame_shape=frame_shape,
                resize_scale=resize_scale,
                pad_x=pad_x,
                pad_y=pad_y,
            )
            if width <= 1 or height <= 1:
                left, top, width, height = _restore_cxcywh_box(
                    center_x=float(row[0]),
                    center_y=float(row[1]),
                    width=float(row[2]),
                    height=float(row[3]),
                    frame_shape=frame_shape,
                    resize_scale=resize_scale,
                    pad_x=pad_x,
                    pad_y=pad_y,
                )
            if width <= 1 or height <= 1:
                continue
            parsed_detections.append(
                PersonDetection(
                    left=left,
                    top=top,
                    width=width,
                    height=height,
                    confidence=confidence,
                ),
            )
        return parsed_detections


def _build_letterboxed_blob(
    frame: np.ndarray,
    input_size: int,
) -> tuple[np.ndarray, float, float, float]:
    frame_height, frame_width = frame.shape[:2]
    resize_scale = min(input_size / frame_width, input_size / frame_height)
    resized_width = int(round(frame_width * resize_scale))
    resized_height = int(round(frame_height * resize_scale))
    # OpenCV exposes resize constants dynamically, which pylint cannot introspect.
    # pylint: disable=no-member
    resized = cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((input_size, input_size, 3), 114, dtype=np.uint8)
    pad_x = (input_size - resized_width) / 2.0
    pad_y = (input_size - resized_height) / 2.0
    top = int(round(pad_y - 0.1))
    left = int(round(pad_x - 0.1))
    canvas[top : top + resized_height, left : left + resized_width] = resized
    blob = cv2.dnn.blobFromImage(
        canvas,
        scalefactor=1.0 / 255.0,
        size=(input_size, input_size),
        swapRB=True,
        crop=False,
    )
    return blob, resize_scale, pad_x, pad_y


def _restore_xyxy_box(
    *,
    left: float,
    top: float,
    right: float,
    bottom: float,
    frame_shape: tuple[int, int],
    resize_scale: float,
    pad_x: float,
    pad_y: float,
) -> tuple[int, int, int, int]:
    frame_height, frame_width = frame_shape
    x1 = int(round(max(0.0, min(frame_width, (left - pad_x) / resize_scale))))
    y1 = int(round(max(0.0, min(frame_height, (top - pad_y) / resize_scale))))
    x2 = int(round(max(0.0, min(frame_width, (right - pad_x) / resize_scale))))
    y2 = int(round(max(0.0, min(frame_height, (bottom - pad_y) / resize_scale))))
    return x1, y1, max(0, x2 - x1), max(0, y2 - y1)


def _restore_cxcywh_box(
    *,
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    frame_shape: tuple[int, int],
    resize_scale: float,
    pad_x: float,
    pad_y: float,
) -> tuple[int, int, int, int]:
    left = center_x - (width / 2.0)
    top = center_y - (height / 2.0)
    right = center_x + (width / 2.0)
    bottom = center_y + (height / 2.0)
    return _restore_xyxy_box(
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        frame_shape=frame_shape,
        resize_scale=resize_scale,
        pad_x=pad_x,
        pad_y=pad_y,
    )


def _select_indices(
    detections: list[PersonDetection],
    keep_indices: np.ndarray | tuple | list,
) -> list[PersonDetection]:
    if len(detections) == 0 or len(keep_indices) == 0:
        return []

    flattened_indices = np.array(keep_indices).reshape(-1)
    return [detections[int(index)] for index in flattened_indices]
