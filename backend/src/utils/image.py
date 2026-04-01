from __future__ import annotations

import numpy as np


def clamp_ltwh_to_frame(
    frame_shape: tuple[int, int],
    left: int,
    top: int,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    """Clamp a left-top-width-height box so it fits inside a frame."""

    frame_height, frame_width = frame_shape
    clamped_left = max(0, min(frame_width, left))
    clamped_top = max(0, min(frame_height, top))
    clamped_right = max(clamped_left, min(frame_width, left + width))
    clamped_bottom = max(clamped_top, min(frame_height, top + height))
    return (
        clamped_left,
        clamped_top,
        max(0, clamped_right - clamped_left),
        max(0, clamped_bottom - clamped_top),
    )


def crop_ltwh(
    frame: np.ndarray,
    left: int,
    top: int,
    width: int,
    height: int,
) -> np.ndarray | None:
    """Return a cropped frame chip for a valid left-top-width-height box."""

    clamped_left, clamped_top, clamped_width, clamped_height = clamp_ltwh_to_frame(
        frame.shape[:2],
        left,
        top,
        width,
        height,
    )
    if clamped_width <= 0 or clamped_height <= 0:
        return None
    return frame[
        clamped_top : clamped_top + clamped_height,
        clamped_left : clamped_left + clamped_width,
    ].copy()
