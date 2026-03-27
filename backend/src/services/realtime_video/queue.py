"""In-memory queue primitives for sampled frames."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum

from src.services.realtime_video.contracts import FrameSample


class QueueDropPolicy(str, Enum):
    """Supported backpressure strategies for the frame queue."""

    drop_oldest = "drop_oldest"
    drop_newest = "drop_newest"
    block = "block"


@dataclass(slots=True)
class QueueMetrics:
    """Runtime counters for the in-memory frame queue."""

    published_frames: int = 0
    dropped_frames: int = 0


class FrameQueue:
    """Bounded asynchronous queue for sampled frames."""

    def __init__(
        self,
        maxsize: int = 512,
        drop_policy: QueueDropPolicy = QueueDropPolicy.drop_oldest,
    ) -> None:
        """Create a bounded queue with a deterministic backpressure policy."""

        self._queue: asyncio.Queue[FrameSample] = asyncio.Queue(maxsize=maxsize)
        self._drop_policy = drop_policy
        self._metrics = QueueMetrics()

    async def publish(self, frame: FrameSample) -> bool:
        """Publish a frame into the queue according to the configured drop policy."""

        if self._drop_policy == QueueDropPolicy.block:
            await self._queue.put(frame)
            self._metrics.published_frames += 1
            return True
        return self.publish_nowait(frame)

    def publish_nowait(self, frame: FrameSample) -> bool:
        """Publish a frame immediately without awaiting on queue backpressure."""

        if self._queue.full():
            if self._drop_policy in {
                QueueDropPolicy.block,
                QueueDropPolicy.drop_newest,
            }:
                self._metrics.dropped_frames += 1
                return False
            self._queue.get_nowait()
            self._queue.task_done()
            self._metrics.dropped_frames += 1

        self._queue.put_nowait(frame)
        self._metrics.published_frames += 1
        return True

    async def consume(self) -> FrameSample:
        """Consume the next sampled frame from the queue."""

        frame = await self._queue.get()
        self._queue.task_done()
        return frame

    async def iter_frames(self) -> AsyncIterator[FrameSample]:
        """Yield frames forever from the queue in consumer order."""

        while True:
            yield await self.consume()

    def metrics(self) -> QueueMetrics:
        """Return a snapshot of queue metrics."""

        return QueueMetrics(
            published_frames=self._metrics.published_frames,
            dropped_frames=self._metrics.dropped_frames,
        )

    def qsize(self) -> int:
        """Return the current queue depth."""

        return self._queue.qsize()
