"""Helper for reading frames from SharedMemory."""
from __future__ import annotations

import numpy as np
from libs.shared.shm.ring_buffer import RingBufferReader

class SHMReader:
    def __init__(self, camera_id: str, slots: int, h: int, w: int) -> None:
        self._reader = RingBufferReader(camera_id, slots, h, w)

    def read_frame(self, slot_idx: int) -> np.ndarray:
        return self._reader.read(slot_idx)
