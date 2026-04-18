"""Bounded thread-safe frame buffers with explicit backpressure policies."""

from __future__ import annotations

import asyncio
import threading
from queue import Empty, Full, Queue

from src.opencv_pipeline.contracts import DropPolicy, FramePacket


class FrameBuffer:
    """Thread-safe bounded queue between capture and processing stages.

    Internally uses a thread-safe queue.Queue for storage (safe for use from
    capture threads) and an asyncio Event for efficient event-driven wakeup in
    the pipeline loop.

    - publish() is safe to call from a background capture thread.
    - get() must be called from an async context.
    """

    def __init__(
        self,
        maxsize: int,
        drop_policy: DropPolicy = DropPolicy.drop_oldest,
    ) -> None:
        self._queue: Queue[FramePacket] = Queue(maxsize=max(maxsize, 1))
        self._drop_policy = drop_policy
        self._event: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._init_lock = threading.Lock()

    def _ensure_loop_initialized(self) -> None:
        """Cache the running event loop lazily (called from async context)."""
        if self._loop is None:
            with self._init_lock:
                if self._loop is None:
                    self._loop = asyncio.get_running_loop()

    def publish(self, packet: FramePacket) -> bool:
        """Publish a frame packet from a capture thread.

        Uses the thread-safe queue.Queue; notifies the asyncio Event so
        that any get() coroutine waiting on it wakes up immediately.
        """

        try:
            self._queue.put_nowait(packet)
        except Full:
            if self._drop_policy == DropPolicy.drop_newest:
                return False
            if self._drop_policy == DropPolicy.block:
                self._queue.put(packet)
                self._wakeup()
                return True
            # drop_oldest: evict oldest before enqueueing
            try:
                self._queue.get_nowait()
            except Empty:
                pass
            try:
                self._queue.put_nowait(packet)
            except Full:
                return False

        self._wakeup()
        return True

    def _wakeup(self) -> None:
        """Signal the asyncio pipeline that a frame is available.

        Uses call_soon_threadsafe so it is safe to call from a capture thread.
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        event = self._event
        if event is None:
            return
        loop.call_soon_threadsafe(event.set)

    async def get(self) -> FramePacket:
        """Await and return the next published frame packet.

        Waits efficiently on an asyncio Event rather than polling. The event is
        lazily initialized on first call so that this method
        can safely be called from the pipeline's async context.
        """
        if self._event is None:
            self._event = asyncio.Event()
        self._ensure_loop_initialized()

        event = self._event
        while True:
            try:
                return self._queue.get_nowait()
            except Empty:
                event.clear()
                if not self._queue.empty():
                    continue
                await event.wait()

    def qsize(self) -> int:
        """Return the current queue depth."""
        return self._queue.qsize()

    def empty(self) -> bool:
        """Return True if the queue is empty (approximate snapshot)."""
        return self._queue.empty()

    def discard_camera(self, camera_id: str) -> int:
        """Remove queued frames for a camera that has left the active set."""

        with self._queue.mutex:
            original_size = len(self._queue.queue)
            self._queue.queue = type(self._queue.queue)(
                packet
                for packet in self._queue.queue
                if packet.camera_id != camera_id
            )
            removed = original_size - len(self._queue.queue)
            self._queue.unfinished_tasks = max(0, self._queue.unfinished_tasks - removed)
            if removed:
                self._queue.not_full.notify_all()
            return removed
