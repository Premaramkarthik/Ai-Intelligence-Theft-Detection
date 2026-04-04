"""Pool of PersonDetector instances — one checked out per camera worker."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from src.services.tracking.contracts import PersonDetector


class DetectorPool:
    """Hold N detector instances and limit concurrent checkout via asyncio.Semaphore.

    The pool is sized to the number of detectors supplied.  Each call to
    acquire() or get() checks one instance out; it must be returned via
    the context manager exit or an explicit put() call.
    """

    def __init__(self, detectors: list[PersonDetector]) -> None:
        if not detectors:
            raise ValueError("DetectorPool requires at least one detector.")
        self._detectors = list(detectors)
        self._semaphore = asyncio.Semaphore(len(detectors))
        self._available: asyncio.Queue[PersonDetector] = asyncio.Queue()
        for detector in self._detectors:
            self._available.put_nowait(detector)

    # ------------------------------------------------------------------
    # Context-manager API (preferred)
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[PersonDetector]:
        """Check out a detector; automatically return it on context exit."""
        async with self._semaphore:
            detector = await self._available.get()
            try:
                yield detector
            finally:
                self._available.put_nowait(detector)

    # ------------------------------------------------------------------
    # Manual checkout API (for callers with non-trivial lifetimes)
    # ------------------------------------------------------------------

    async def get(self) -> PersonDetector:
        """Check out a detector.  Caller must call put() when finished."""
        await self._semaphore.acquire()
        return await self._available.get()

    def put(self, detector: PersonDetector) -> None:
        """Return a previously checked-out detector to the pool."""
        self._available.put_nowait(detector)
        self._semaphore.release()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def size(self) -> int:
        """Total number of detectors in the pool (checked out or available)."""
        return len(self._detectors)

    def available(self) -> int:
        """Number of detectors currently available for checkout."""
        return self._available.qsize()
