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

_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _prepare_temporal_window(frames: list[Any], *, required: int) -> tuple[list[Any], int]:
    """Return exactly ``required`` frames padded by repetition, plus the pad count."""

    if not frames:
        raise ValueError("Inference batch builder requires at least one frame crop.")
    if len(frames) >= required:
        return list(frames[-required:]), 0
    padded = list(frames)
    pad_count = required - len(frames)
    padded.extend([frames[-1]] * pad_count)
    return padded, pad_count


def _resize_crop(crop: Any, *, h: int, w: int) -> np.ndarray:
    """Resize a HWC BGR uint8 ndarray to ``(h, w, 3)`` RGB, rescale and normalise."""

    import cv2  # pylint: disable=import-outside-toplevel

    resized: np.ndarray = cv2.resize(crop, (w, h), interpolation=cv2.INTER_LINEAR)
    if resized.ndim == 2:
        resized = np.stack([resized] * 3, axis=-1)
    resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    return (resized.astype(np.float32) / 255.0 - _IMAGENET_MEAN) / _IMAGENET_STD


class BatchBuilder:
    """Build normalised Triton input tensors from a list of frame crops.

    Current model contracts in ``backend/model_repository/triton``:
    - ``cnn_transformer`` expects ``input`` shaped ``(1, 16, 3, 224, 224)``
    - ``vjepa_probe`` maps to ``vjepa_finetune`` and expects
      ``pixel_values_videos`` shaped ``(1, 16, 3, 256, 256)``

    Short temporal windows are padded by repeating the most recent crop so
    inference can start immediately when a person first appears.
    """

    def build(
        self,
        frames: list[Any],
        strategy: str,
    ) -> tuple[dict[str, np.ndarray], dict[str, int]]:
        """Return ``(named_tensors, metadata)`` for ``strategy``.

        ``metadata`` contains:
        - ``real_frames``: number of actual frames supplied
        - ``padded_frames``: number of frames added by repetition padding
        """

        if strategy == "vjepa_probe":
            tensor, padded = self._build_vjepa_tensor(frames)
            meta = {"real_frames": len(frames), "padded_frames": padded}
            return {"pixel_values_videos": tensor}, meta

        tensor, padded = self._build_cnn_transformer_tensor(frames)
        meta = {"real_frames": len(frames), "padded_frames": padded}
        return {"input": tensor}, meta

    def _build_cnn_transformer_tensor(self, frames: list[Any]) -> tuple[np.ndarray, int]:
        """Build the CNN transformer tensor as ``(1, T, C, H, W)``."""

        prepared_frames, pad_count = _prepare_temporal_window(frames, required=_CNN_TEMPORAL_WINDOW)
        resized = np.stack(
            [_resize_crop(frame, h=_CNN_CROP_H, w=_CNN_CROP_W) for frame in prepared_frames],
            axis=0,
        )  # (T, H, W, C)
        return resized.transpose(0, 3, 1, 2)[np.newaxis], pad_count  # (1, T, C, H, W)

    def _build_vjepa_tensor(self, frames: list[Any]) -> tuple[np.ndarray, int]:
        """Build the VJEPA tensor as ``(1, T, C, H, W)``."""

        prepared_frames, pad_count = _prepare_temporal_window(frames, required=_VJEPA_TEMPORAL_WINDOW)
        resized = np.stack(
            [_resize_crop(frame, h=_VJEPA_CROP_H, w=_VJEPA_CROP_W) for frame in prepared_frames],
            axis=0,
        )  # (T, H, W, C)
        return resized.transpose(0, 3, 1, 2)[np.newaxis], pad_count  # (1, T, C, H, W)
