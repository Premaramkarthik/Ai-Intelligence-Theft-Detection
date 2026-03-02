"""
shared.shm — Zero-copy shared-memory ring buffer transport.

    from shared.shm import RingBufferWriter, RingBufferReader, ReaderCache
"""
from shared.shm.ring_buffer import (
    RingBufferWriter,
    RingBufferReader,
    ReaderCache,
    SLOT_DTYPE,
)

__all__ = [
    "RingBufferWriter",
    "RingBufferReader",
    "ReaderCache",
    "SLOT_DTYPE",
]
