"""Motion analysis using Farneback optical flow and background subtraction."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from src.opencv_pipeline.contracts import MotionSummary, ProcessedFrame


@dataclass(slots=True)
class _MotionState:
    prev_gray: np.ndarray | None
    background_subtractor: cv2.BackgroundSubtractor


class MotionAnalyzer:
    """Estimate motion consistency and foreground activity per camera."""

    def __init__(
        self,
        *,
        background_model: str = "mog2",
        flow_consistency_std_threshold: float = 4.0,
    ) -> None:
        self._background_model = background_model
        self._flow_consistency_std_threshold = flow_consistency_std_threshold
        self._states: dict[str, _MotionState] = {}

    def analyze(self, processed_frame: ProcessedFrame) -> MotionSummary:
        """Return motion features for the current camera frame."""

        camera_id = processed_frame.packet.camera_id
        state = self._states.get(camera_id)
        if state is None:
            state = _MotionState(
                prev_gray=None,
                background_subtractor=_build_background_subtractor(self._background_model),
            )
            self._states[camera_id] = state

        foreground_mask = state.background_subtractor.apply(processed_frame.working_bgr)
        foreground_ratio = float(cv2.countNonZero(foreground_mask)) / float(foreground_mask.size)

        if state.prev_gray is None:
            state.prev_gray = processed_frame.gray
            return MotionSummary(
                foreground_ratio=foreground_ratio,
                is_motion_consistent=foreground_ratio < 0.75,
            )

        flow = cv2.calcOpticalFlowFarneback(
            state.prev_gray,
            processed_frame.gray,
            None,
            0.5,
            3,
            15,
            3,
            5,
            1.2,
            0,
        )
        state.prev_gray = processed_frame.gray

        magnitude, _angle = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        flow_mask = foreground_mask > 0
        sampled_magnitude = magnitude[flow_mask] if np.any(flow_mask) else magnitude.reshape(-1)
        mean_magnitude = float(sampled_magnitude.mean()) if sampled_magnitude.size else 0.0
        dominant_dx = float(np.median(flow[..., 0]))
        dominant_dy = float(np.median(flow[..., 1]))
        magnitude_std = float(sampled_magnitude.std()) if sampled_magnitude.size else 0.0
        is_consistent = magnitude_std <= self._flow_consistency_std_threshold

        return MotionSummary(
            mean_magnitude=mean_magnitude,
            dominant_dx=dominant_dx,
            dominant_dy=dominant_dy,
            foreground_ratio=foreground_ratio,
            is_motion_consistent=is_consistent,
        )

    def remove_camera(self, camera_id: str) -> None:
        """Discard optical-flow and background-subtractor state for a removed camera."""

        self._states.pop(camera_id, None)


def _build_background_subtractor(background_model: str) -> cv2.BackgroundSubtractor:
    normalized = background_model.strip().lower()
    if normalized != "mog2":
        bgsegm_module = getattr(cv2, "bgsegm", None)
        factory_name = {
            "cnt": "createBackgroundSubtractorCNT",
            "gsoc": "createBackgroundSubtractorGSOC",
            "mog": "createBackgroundSubtractorMOG",
            "lsbp": "createBackgroundSubtractorLSBP",
        }.get(normalized)
        if bgsegm_module is not None and factory_name is not None:
            factory = getattr(bgsegm_module, factory_name, None)
            if callable(factory):
                return factory()
    return cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=16.0, detectShadows=True)
