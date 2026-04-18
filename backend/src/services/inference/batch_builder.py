"""Assemble Triton input tensors for each inference strategy."""

from __future__ import annotations

from typing import Any

import numpy as np


_CNN_TEMPORAL_WINDOW = 16
_CNN_CROP_H = 224
_CNN_CROP_W = 224
_VJEPA_TEMPORAL_WINDOW = 16
_VJEPA_CROP_H = 256
_VJEPA_CROP_W = 256


def _resize_crop(crop: Any, *, h: int, w: int) -> np.ndarray:
    """Resize a HWC uint8 ndarray to ``(h, w, 3)`` and normalise to FP32."""

    import cv2  # pylint: disable=import-outside-toplevel

    resized: np.ndarray = cv2.resize(crop, (w, h), interpolation=cv2.INTER_LINEAR)
    if resized.ndim == 2:
        resized = np.stack([resized] * 3, axis=-1)
    return resized.astype(np.float32) / 255.0


class BatchBuilder:
    """Build normalised Triton input tensors from a list of frame crops.

    Current model contracts in ``backend/model_repository/triton``:
    - ``cnn_transformer`` expects ``input`` shaped ``(1, 16, 3, 224, 224)``
    - ``vjepa_probe`` maps to ``vjepa_finetune`` and expects
      ``pixel_values_videos`` shaped ``(1, 16, 3, 256, 256)``
    """

    def build(
        self,
        frames: list[Any],
        strategy: str,
    ) -> dict[str, np.ndarray]:
        """Return the named Triton tensors for ``strategy``."""

        if strategy == "vjepa_probe":
            tensor = self._build_vjepa_tensor(frames)
            return {"pixel_values_videos": tensor}

        tensor = self._build_cnn_transformer_tensor(frames)
        return {"input": tensor}

    def _build_cnn_transformer_tensor(self, frames: list[Any]) -> np.ndarray:
        """Build the CNN transformer tensor as ``(1, T, C, H, W)``."""

        resized = np.stack(
            [_resize_crop(frame, h=_CNN_CROP_H, w=_CNN_CROP_W) for frame in frames],
            axis=0,
        )  # (T, H, W, C)
        if resized.shape[0] != _CNN_TEMPORAL_WINDOW:
            raise ValueError(
                "cnn_transformer expects exactly "
                f"{_CNN_TEMPORAL_WINDOW} frames, got {resized.shape[0]}."
            )
        return resized.transpose(0, 3, 1, 2)[np.newaxis]  # (1, T, C, H, W)

    def _build_vjepa_tensor(self, frames: list[Any]) -> np.ndarray:
        """Build the VJEPA tensor as ``(1, T, C, H, W)``."""

        resized = np.stack(
            [_resize_crop(frame, h=_VJEPA_CROP_H, w=_VJEPA_CROP_W) for frame in frames],
            axis=0,
        )  # (T, H, W, C)
        if resized.shape[0] != _VJEPA_TEMPORAL_WINDOW:
            raise ValueError(
                f"vjepa_probe expects exactly {_VJEPA_TEMPORAL_WINDOW} frames, "
                f"got {resized.shape[0]}."
            )
        return resized.transpose(0, 3, 1, 2)[np.newaxis]  # (1, T, C, H, W)
