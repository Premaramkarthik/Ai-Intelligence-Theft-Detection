"""Assemble Triton input tensors for each inference strategy."""

from __future__ import annotations

from typing import Any

import numpy as np


# Target spatial size shared by both strategies.
_CROP_H = 224
_CROP_W = 224

# V-JEPA expects (B, T, C, H, W); CNN-transformer expects (B, C, T, H, W).
_VJEPA_FRAME_DIM = 16
_CNN_FRAME_DIM = 16


def _resize_crop(crop: Any, h: int = _CROP_H, w: int = _CROP_W) -> np.ndarray:
    """Resize a HWC uint8 ndarray to (h, w, 3) via simple nearest-neighbour."""
    import cv2  # pylint: disable=import-outside-toplevel

    resized: np.ndarray = cv2.resize(crop, (w, h), interpolation=cv2.INTER_LINEAR)
    if resized.ndim == 2:
        resized = np.stack([resized] * 3, axis=-1)
    return resized.astype(np.float32) / 255.0


class BatchBuilder:
    """Build normalised Triton input tensors from a list of frame crops.

    cnn_transformer input shape: (1, C, T, H, W) — BCTHW
    vjepa_probe input shape:     (1, T, C, H, W) — BTCHW
    """

    def build(
        self,
        frames: list[Any],
        strategy: str,
    ) -> dict[str, np.ndarray]:
        """Return a dict mapping Triton input name → numpy array.

        Args:
            frames: list of HWC uint8 numpy arrays (length == temporal window).
            strategy: "cnn_transformer" or "vjepa_probe".

        Returns:
            {"input": np.ndarray} with the expected spatial-temporal shape.
        """
        resized = np.stack([_resize_crop(f) for f in frames], axis=0)  # (T, H, W, C)

        if strategy == "vjepa_probe":
            # BTCHW: (1, T, C, H, W)
            tensor = resized.transpose(0, 3, 1, 2)[np.newaxis]  # (1, T, C, H, W)
        else:
            # BCTHW: (1, C, T, H, W)
            tensor = resized.transpose(3, 0, 1, 2)[np.newaxis]  # (1, C, T, H, W)

        return {"input": tensor}
