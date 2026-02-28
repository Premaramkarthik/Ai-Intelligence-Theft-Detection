"""
Shared memory ring-buffer — zero-copy frame transport between MediaBridge and Inference.
MediaBridge writes raw NumPy ROI frames; Inference reads them by slot pointer.

Layout (per camera):
    shm_name = f"cam_{camera_id}_ring"
    slots: N fixed-size buffers, each = H * W * C bytes
    write_idx: stored in a separate tiny shm block (1 int64)
"""
from __future__ import annotations

import ctypes
import multiprocessing.shared_memory as mp_shm
from typing import Final

import numpy as np


SLOT_DTYPE: Final = np.uint8


class RingBufferWriter:
    """
    MediaBridge side — writes ROI frames into the ring buffer.

    Responsibilities (SRP):
        - Allocate or attach to shared memory on init.
        - Write one frame per call, advancing the slot index atomically.
    """

    def __init__(self, camera_id: str, num_slots: int, frame_height: int, frame_width: int) -> None:
        self.camera_id = camera_id
        self.num_slots = num_slots
        self.frame_shape = (frame_height, frame_width, 3)  # Assuming BGR/RGB
        self.frame_bytes = int(np.prod(self.frame_shape))
        self.shm_name = f"cam_{camera_id}_ring"
        self.idx_name = f"cam_{camera_id}_idx"

        # Allocate frame data block
        try:
            self._shm = mp_shm.SharedMemory(
                name=self.shm_name,
                create=True,
                size=num_slots * self.frame_bytes,
            )
        except FileExistsError:
            # Cleanup stale segment and retry
            stale = mp_shm.SharedMemory(name=self.shm_name)
            stale.close()
            stale.unlink()
            self._shm = mp_shm.SharedMemory(
                name=self.shm_name,
                create=True,
                size=num_slots * self.frame_bytes,
            )

        # Allocate atomic index block (1 × int64)
        try:
            self._idx_shm = mp_shm.SharedMemory(
                name=self.idx_name,
                create=True,
                size=ctypes.sizeof(ctypes.c_int64),
            )
        except FileExistsError:
            stale = mp_shm.SharedMemory(name=self.idx_name)
            stale.close()
            stale.unlink()
            self._idx_shm = mp_shm.SharedMemory(
                name=self.idx_name,
                create=True,
                size=ctypes.sizeof(ctypes.c_int64),
            )
        
        self._idx_array = np.ndarray((1,), dtype=np.int64, buffer=self._idx_shm.buf)
        self._idx_array[0] = 0

    def write(self, frame: np.ndarray) -> int:
        """Write frame to next slot; returns the slot_id written."""
        slot_id = int(self._idx_array[0]) % self.num_slots
        offset = slot_id * self.frame_bytes
        buf = np.ndarray(self.frame_shape, dtype=SLOT_DTYPE, buffer=self._shm.buf, offset=offset)
        np.copyto(buf, frame)
        # Advance the index (wraparound handled by modulo on read)
        self._idx_array[0] += 1
        return slot_id

    def close(self) -> None:
        self._shm.close()
        self._shm.unlink()
        self._idx_shm.close()
        self._idx_shm.unlink()


class RingBufferReader:
    """
    Inference side — reads frames from a slot by ID.

    Responsibilities (SRP):
        - Attach to an existing shared memory block (created by writer).
        - Return a zero-copy NumPy view of the requested slot.
    """

    def __init__(self, camera_id: str, num_slots: int, frame_height: int, frame_width: int) -> None:
        self.camera_id = camera_id
        self.num_slots = num_slots
        self.frame_shape = (frame_height, frame_width, 3)
        self.frame_bytes = int(np.prod(self.frame_shape))
        self.shm_name = f"cam_{camera_id}_ring"

        try:
            self._shm = mp_shm.SharedMemory(name=self.shm_name, create=False)
            # Use cached logger to avoid overhead
            from shared.logging.logger import get_logger
            get_logger(__name__).debug("RingBufferReader attached", extra={"shm": self.shm_name})
        except FileNotFoundError:
            raise FileNotFoundError(f"Shared memory segment '{self.shm_name}' not found. Is MediaBridge running for {camera_id}?")

    def read(self, slot_id: int) -> np.ndarray:
        """Return a zero-copy NumPy view of the frame at slot_id."""
        offset = (slot_id % self.num_slots) * self.frame_bytes
        return np.ndarray(self.frame_shape, dtype=SLOT_DTYPE, buffer=self._shm.buf, offset=offset)

    def close(self) -> None:
        try:
            self._shm.close()
        except:
            pass

class ReaderCache:
    """Thread-safe cache for RingBufferReader instances."""
    _readers: dict[str, RingBufferReader] = {}

    @classmethod
    def get_reader(cls, camera_id: str, num_slots: int, h: int, w: int) -> RingBufferReader:
        if camera_id not in cls._readers:
            import time
            last_err = FileNotFoundError("Unknown error")
            for _ in range(3):
                try:
                    cls._readers[camera_id] = RingBufferReader(camera_id, num_slots, h, w)
                    return cls._readers[camera_id]
                except FileNotFoundError as e:
                    last_err = e
                    time.sleep(1)
            raise last_err
        return cls._readers[camera_id]

    @classmethod
    def clear(cls):
        for reader in cls._readers.values():
            reader.close()
        cls._readers.clear()
