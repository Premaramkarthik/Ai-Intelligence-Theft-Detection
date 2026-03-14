"""SHMWriter wrapper for the MediaBridge service."""
from __future__ import annotations

import numpy as np
from shared.shm.ring_buffer import RingBufferWriter

class SHMWriter:
    def __init__(self, camera_id: str, slots: int, h: int, w: int) -> None:
        self._writer = RingBufferWriter(camera_id, slots, h, w)

    def write(self, frame: np.ndarray) -> tuple[int, int]:
        return self._writer.write(frame)

    def close(self) -> None:
        self._writer.close()
