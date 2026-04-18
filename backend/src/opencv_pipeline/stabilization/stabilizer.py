"""Video stabilization using Lucas-Kanade optical flow and affine warping."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from src.opencv_pipeline.contracts import ProcessedFrame
from src.opencv_pipeline.preprocessing.processor import FramePreprocessor


@dataclass(slots=True)
class _StabilizerState:
    prev_gray: np.ndarray | None = None
    previous_transform: np.ndarray | None = None


class OpticalFlowStabilizer:
    """Stabilize frames per camera with feature tracking and affine transforms."""

    def __init__(
        self,
        preprocessor: FramePreprocessor,
        *,
        max_corners: int = 200,
        quality_level: float = 0.01,
        min_distance: float = 30.0,
        min_points: int = 12,
        smoothing_alpha: float = 0.3,
    ) -> None:
        self._preprocessor = preprocessor
        self._max_corners = max_corners
        self._quality_level = quality_level
        self._min_distance = min_distance
        self._min_points = min_points
        self._smoothing_alpha = min(max(smoothing_alpha, 0.0), 1.0)
        self._states: dict[str, _StabilizerState] = {}

    def stabilize(self, processed_frame: ProcessedFrame) -> tuple[ProcessedFrame, np.ndarray | None]:
        """Return a stabilized frame plus the affine transform that was applied."""

        camera_id = processed_frame.packet.camera_id
        state = self._states.setdefault(camera_id, _StabilizerState())
        current_gray = processed_frame.gray

        if state.prev_gray is None:
            state.prev_gray = current_gray
            return processed_frame, None

        prev_points = cv2.goodFeaturesToTrack(
            state.prev_gray,
            maxCorners=self._max_corners,
            qualityLevel=self._quality_level,
            minDistance=self._min_distance,
        )
        if prev_points is None or len(prev_points) < self._min_points:
            state.prev_gray = current_gray
            return processed_frame, None

        next_points, status, _ = cv2.calcOpticalFlowPyrLK(
            state.prev_gray,
            current_gray,
            prev_points,
            None,
        )
        if next_points is None or status is None:
            state.prev_gray = current_gray
            return processed_frame, None

        valid_prev = prev_points[status.flatten() == 1]
        valid_next = next_points[status.flatten() == 1]
        if len(valid_prev) < self._min_points:
            state.prev_gray = current_gray
            return processed_frame, None

        transform, _ = cv2.estimateAffinePartial2D(valid_prev, valid_next)
        if transform is None:
            state.prev_gray = current_gray
            return processed_frame, None

        smoothed_transform = _smooth_transform(
            transform.astype(np.float32),
            state.previous_transform,
            self._smoothing_alpha,
        )
        if _is_near_identity(smoothed_transform):
            state.prev_gray = current_gray
            state.previous_transform = smoothed_transform
            return processed_frame, None

        height, width = processed_frame.working_bgr.shape[:2]
        stabilized = cv2.warpAffine(
            processed_frame.working_bgr,
            smoothed_transform,
            (width, height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REFLECT,
        )
        world_reference_frame = processed_frame.world_reference_frame
        if world_reference_frame is not None:
            world_reference_frame = cv2.warpAffine(
                world_reference_frame,
                smoothed_transform,
                (world_reference_frame.shape[1], world_reference_frame.shape[0]),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REFLECT,
            )

        state.prev_gray = current_gray
        state.previous_transform = smoothed_transform
        return (
            self._preprocessor.refresh(
                processed_frame,
                stabilized,
                world_reference_frame=world_reference_frame,
            ),
            smoothed_transform,
        )

    def remove_camera(self, camera_id: str) -> None:
        """Discard optical-flow history for a removed camera."""

        self._states.pop(camera_id, None)


def _is_near_identity(transform: np.ndarray, translation_threshold: float = 0.5, rotation_threshold: float = 0.003) -> bool:
    """Return True when the transform is too small to warrant a warpAffine call.

    Skipping near-identity warps eliminates per-frame interpolation blur on
    static or slow-moving scenes — the dominant source of softness in CCTV feeds.
    """
    tx, ty = float(transform[0, 2]), float(transform[1, 2])
    cos_theta = float(transform[0, 0])
    sin_theta = float(transform[1, 0])
    translation_magnitude = (tx ** 2 + ty ** 2) ** 0.5
    rotation_magnitude = abs(sin_theta) + abs(1.0 - cos_theta)
    return translation_magnitude < translation_threshold and rotation_magnitude < rotation_threshold


def _smooth_transform(
    current: np.ndarray,
    previous: np.ndarray | None,
    alpha: float,
) -> np.ndarray:
    """Exponential-moving-average (EMA) transform smoothing.

    The formula is: smoothed = alpha * current + (1-alpha) * previous
    This means alpha controls how much the NEW (current) transform contributes.
    Lower alpha = more smoothing but more lag; higher alpha = more responsive
    but jittery.  For real-time CCTV stabilization, 0.3-0.5 is typical.

    Reference: RidgeRun Video Stabilization Library, Gyroflow adaptive smoothing.
    """
    if previous is None:
        return current
    return (alpha * current) + ((1.0 - alpha) * previous)
