"""Image preprocessing utilities built on OpenCV imgproc."""

from __future__ import annotations

from dataclasses import replace

import cv2
import numpy as np

from src.opencv_pipeline.contracts import CalibrationProfile, FramePacket, ProcessedFrame


class FramePreprocessor:
    """Resize, color-convert, and normalize frames for downstream stages."""

    def __init__(
        self,
        *,
        target_width: int,
        target_height: int,
        low_light_threshold: float = 40.0,
    ) -> None:
        self._target_width = target_width
        self._target_height = target_height
        self._low_light_threshold = low_light_threshold

    def process(
        self,
        packet: FramePacket,
        *,
        calibration: CalibrationProfile | None,
        frame_bgr: np.ndarray | None = None,
    ) -> ProcessedFrame:
        """Convert a raw frame into the shared processed-frame contract."""

        raw_bgr = packet.frame_bgr if frame_bgr is None else frame_bgr
        working_bgr = cv2.resize(
            raw_bgr,
            (self._target_width, self._target_height),
            interpolation=cv2.INTER_LINEAR,
        )
        rgb = cv2.cvtColor(working_bgr, cv2.COLOR_BGR2RGB)
        gray = cv2.cvtColor(working_bgr, cv2.COLOR_BGR2GRAY)
        normalized_rgb = rgb.astype(np.float32) / 255.0
        low_light = float(gray.mean()) < self._low_light_threshold
        return ProcessedFrame(
            packet=packet,
            calibration=calibration,
            raw_bgr=raw_bgr,
            working_bgr=working_bgr,
            rgb=rgb,
            normalized_rgb=normalized_rgb,
            gray=gray,
            low_light=low_light,
        )

    def refresh(
        self,
        processed_frame: ProcessedFrame,
        frame_bgr: np.ndarray,
        *,
        world_reference_frame: np.ndarray | None = None,
    ) -> ProcessedFrame:
        """Recompute derived color spaces after a downstream frame transform."""

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        normalized_rgb = rgb.astype(np.float32) / 255.0
        low_light = float(gray.mean()) < self._low_light_threshold
        return replace(
            processed_frame,
            working_bgr=frame_bgr,
            rgb=rgb,
            normalized_rgb=normalized_rgb,
            gray=gray,
            low_light=low_light,
            world_reference_frame=world_reference_frame,
        )
