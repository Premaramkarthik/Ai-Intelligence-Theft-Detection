"""
TemporalBuffer — Circular frame buffer for video clips.
Moved from services.inference.temporal.temporal_buffer
"""
from __future__ import annotations

from collections import deque
import numpy as np

class TemporalBuffer:
    def __init__(self, maxlen: int = 16) -> None:
        self._buffer: deque[np.ndarray] = deque(maxlen=maxlen)

    def push(self, frame: np.ndarray) -> None:
        self._buffer.append(frame.copy())

    def get_clip(self) -> list[np.ndarray]:
        return list(self._buffer)

    def __len__(self) -> int:
        return len(self._buffer)
