"""Rolling temporal buffer keyed by persistent_id for inference dispatch."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

from src.services.inference.contracts import InferenceIngressSample


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TemporalBufferService:
    """Maintain a 16-frame rolling window of crops per persistent identity.

    Buffer rules (per plan §3.4):
    - Keyed by persistent_id.
    - 16-frame rolling window — oldest frame evicted when full.
    - Buffer continues across camera changes for the same persistent_id.
    - Reset on: 2-second identity gap OR persistent_id_state → "pending".
    - Strategy switch does NOT flush the buffer.
    """

    def __init__(self, window_size: int = 16, gap_reset_seconds: float = 2.0) -> None:
        self._window_size = window_size
        self._gap_reset_seconds = gap_reset_seconds
        self._buffers: dict[str, deque[InferenceIngressSample]] = {}
        self._last_seen: dict[str, datetime] = {}

    def push(self, sample: InferenceIngressSample) -> None:
        """Add a sample to the rolling buffer for its persistent_id."""
        pid = sample.persistent_id
        now = sample.sampled_at

        if pid in self._last_seen:
            gap = (now - self._last_seen[pid]).total_seconds()
            if gap > self._gap_reset_seconds or sample.persistent_id_state == "pending":
                self._buffers.pop(pid, None)

        if pid not in self._buffers:
            self._buffers[pid] = deque(maxlen=self._window_size)

        self._buffers[pid].append(sample)
        self._last_seen[pid] = now

    def get(self, persistent_id: str) -> list[InferenceIngressSample]:
        """Return a snapshot of the current buffer for a persistent_id."""
        buf = self._buffers.get(persistent_id)
        return list(buf) if buf else []

    def depth(self, persistent_id: str) -> int:
        """Return the number of frames currently buffered for a persistent_id."""
        buf = self._buffers.get(persistent_id)
        return len(buf) if buf else 0

    def reset(self, persistent_id: str) -> None:
        """Explicitly evict the buffer for a persistent_id."""
        self._buffers.pop(persistent_id, None)
        self._last_seen.pop(persistent_id, None)

    def evict_stale(self, cutoff_seconds: float) -> None:
        """Remove buffers that have not received an update within cutoff_seconds."""
        now = _utc_now()
        stale = [
            pid
            for pid, ts in self._last_seen.items()
            if (now - ts).total_seconds() > cutoff_seconds
        ]
        for pid in stale:
            self._buffers.pop(pid, None)
            self._last_seen.pop(pid, None)
