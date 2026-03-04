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
        
        # 1. Generate Combined Mask
        if isinstance(masks, list):
            if len(masks) == 0:
                return cv2.GaussianBlur(frame, self._ksize, 0)
            
            # Combine masks at native resolution if possible, or common small resolution
            mask_acc = np.zeros((h, w), dtype=np.uint8)
            for m in masks:
                if m.shape != (h, w):
                    m_resized = cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
                    mask_acc = cv2.bitwise_or(mask_acc, m_resized)
                else:
                    mask_acc = cv2.bitwise_or(mask_acc, (m > 0.5).astype(np.uint8))
            combined = mask_acc
        else:
            # Already a numpy array
            if masks.ndim == 3:
                combined = np.any(masks > 0.5, axis=0).astype(np.uint8)
            else:
                combined = (masks > 0.5).astype(np.uint8)

        # 2. Optimization: Blur a downscaled version if too slow, but here we stay full res
        # for quality unless requested. We use bitwise mask for np.where efficiency.
        blurred = cv2.GaussianBlur(frame, self._ksize, 0)
        
        # fg_mask as 3D for broadcasting
        fg_mask = combined[:, :, np.newaxis].astype(bool)
        return np.where(fg_mask, frame, blurred)
