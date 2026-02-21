"""
BackgroundBlur — applies Gaussian blur to non-person regions.
Moved from services.inference.detection.background_blur
"""
from __future__ import annotations

import cv2
import numpy as np


class BackgroundBlur:
    def __init__(self, ksize: int = 31) -> None:
        if ksize % 2 == 0:
            ksize += 1
        self._ksize = (ksize, ksize)

    def apply(self, frame: np.ndarray, masks: list | np.ndarray) -> np.ndarray:
        """Blur background; keep person regions sharp."""
        h, w = frame.shape[:2]
        if isinstance(masks, list):
            if len(masks) == 0:
                return cv2.GaussianBlur(frame, self._ksize, 0)
            
            # Resize and combine masks efficiently
            resized_masks = []
            for m in masks:
                if m.shape != (h, w):
                    m = cv2.resize(m.astype(np.float32), (w, h))
                resized_masks.append(m > 0.5)
            combined = np.any(resized_masks, axis=0).astype(np.uint8)
        else:
            # Already a numpy array (h, w) or (n, h, w)
            if masks.ndim == 3:
                combined = np.any(masks > 0.5, axis=0).astype(np.uint8)
            else:
                combined = (masks > 0.5).astype(np.uint8)

        # Ensure the final combined mask matches frame resolution
        if combined.shape != (h, w):
            combined = cv2.resize(combined, (w, h), interpolation=cv2.INTER_NEAREST)

        # Batch operations
        blurred = cv2.GaussianBlur(frame, self._ksize, 0)
        fg_mask = combined[:, :, np.newaxis]
        return np.where(fg_mask > 0, frame, blurred).astype(np.uint8)
