"""Bounded thread-safe frame buffers with explicit backpressure policies."""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from multiprocessing import shared_memory
from queue import Empty, Full, Queue

import numpy as np

from src.opencv_pipeline.contracts import DropPolicy, FramePacket


class _SharedMemoryFrameStore:
    """Lazily allocate reusable shared-memory frame slots."""

    def __init__(
        self,
        *,
        frame_shape: tuple[int, int, int],
        frame_dtype: np.dtype,
        max_slots: int,
    ) -> None:
        self._frame_shape = frame_shape
        self._frame_dtype = np.dtype(frame_dtype)
        self._frame_bytes = int(np.prod(frame_shape, dtype=np.int64)) * self._frame_dtype.itemsize
        self._max_slots = max(1, max_slots)
        self._slots: dict[int, shared_memory.SharedMemory] = {}
        self._available: deque[int] = deque()
        self._in_use: set[int] = set()
        self._next_slot_id = 0
        self._condition = threading.Condition()

    @property
    def frame_shape(self) -> tuple[int, int, int]:
        return self._frame_shape

    @property
    def frame_dtype(self) -> np.dtype:
        return self._frame_dtype

    def acquire(self, *, block: bool) -> int | None:
        """Return a slot id or ``None`` when no shared-memory slot is available."""

        with self._condition:
            while True:
                if self._available:
                    slot_id = self._available.popleft()
                    self._in_use.add(slot_id)
                    return slot_id
                if len(self._slots) < self._max_slots:
                    slot_id = self._create_slot_locked()
                    self._in_use.add(slot_id)
                    return slot_id
                if not block:
                    return None
                self._condition.wait()

    def write(self, slot_id: int, frame_bgr: np.ndarray) -> np.ndarray:
        """Copy a frame into a shared-memory slot and return a numpy view."""

        view = self.view(slot_id)
        np.copyto(view, frame_bgr, casting="no")
        return view

    def view(self, slot_id: int) -> np.ndarray:
        """Return a numpy view over the slot's shared-memory block."""

        slot = self._slots[slot_id]
        return np.ndarray(
            self._frame_shape,
            dtype=self._frame_dtype,
            buffer=slot.buf[: self._frame_bytes],
        )

    def release(self, slot_id: int) -> None:
        """Return a shared-memory slot to the reusable pool."""

        with self._condition:
            if slot_id not in self._in_use:
                return
            self._in_use.remove(slot_id)
            self._available.append(slot_id)
            self._condition.notify()

    def close(self) -> None:
        """Close and unlink all created shared-memory blocks."""

        with self._condition:
            slots = list(self._slots.values())
            self._slots.clear()
            self._available.clear()
            self._in_use.clear()
        for slot in slots:
            try:
                slot.close()
            finally:
                try:
                    slot.unlink()
                except FileNotFoundError:
                    pass

    def _create_slot_locked(self) -> int:
        slot_id = self._next_slot_id
        self._next_slot_id += 1
        self._slots[slot_id] = shared_memory.SharedMemory(create=True, size=self._frame_bytes)
        return slot_id


class FrameBuffer:
    """Thread-safe bounded queue between capture and processing stages.

    Internally uses a thread-safe queue.Queue for storage (safe for use from
    capture threads) and an asyncio Event for efficient event-driven wakeup in
    the pipeline loop.

    When shared-memory mode is enabled, packets hold lightweight metadata while
    frame pixels live in lazily-created ``multiprocessing.shared_memory`` slots.

    - publish() is safe to call from a background capture thread.
    - get() must be called from an async context.
    """

    def __init__(
        self,
        maxsize: int,
        drop_policy: DropPolicy = DropPolicy.drop_oldest,
        *,
        use_shared_memory: bool = False,
        frame_shape: tuple[int, int, int] | None = None,
        frame_dtype: np.dtype | str = np.uint8,
        shared_memory_slots: int | None = None,
    ) -> None:
        self._queue: Queue[FramePacket] = Queue(maxsize=max(maxsize, 1))
        self._drop_policy = drop_policy
        self._event: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._init_lock = threading.Lock()
        self._shared_store: _SharedMemoryFrameStore | None = None
        if use_shared_memory:
            if frame_shape is None:
                raise ValueError("frame_shape is required when shared memory is enabled.")
            self._shared_store = _SharedMemoryFrameStore(
                frame_shape=frame_shape,
                frame_dtype=np.dtype(frame_dtype),
                max_slots=shared_memory_slots or maxsize,
            )

    def _ensure_loop_initialized(self) -> None:
        """Cache the running event loop lazily (called from async context)."""
        if self._loop is None:
            with self._init_lock:
                if self._loop is None:
                    self._loop = asyncio.get_running_loop()

    def publish(self, packet: FramePacket) -> bool:
        """Publish a frame packet from a capture thread."""

        queued_packet = self._prepare_packet(packet)
        if queued_packet is None:
            return False

        try:
            self._queue.put_nowait(queued_packet)
        except Full:
            if self._drop_policy == DropPolicy.drop_newest:
                queued_packet.release()
                return False
            if self._drop_policy == DropPolicy.block:
                self._queue.put(queued_packet)
                self._wakeup()
                return True
            # drop_oldest: evict oldest before enqueueing
            try:
                dropped_packet = self._queue.get_nowait()
            except Empty:
                dropped_packet = None
            if dropped_packet is not None:
                dropped_packet.release()
            try:
                self._queue.put_nowait(queued_packet)
            except Full:
                queued_packet.release()
                return False

        self._wakeup()
        return True

    def _prepare_packet(self, packet: FramePacket) -> FramePacket | None:
        shared_store = self._shared_store
        if shared_store is None:
            return packet

        frame_bgr = packet.frame_bgr
        if frame_bgr.shape != shared_store.frame_shape:
            return None
        if frame_bgr.dtype != shared_store.frame_dtype:
            frame_bgr = frame_bgr.astype(shared_store.frame_dtype, copy=False)
        if not frame_bgr.flags.c_contiguous:
            frame_bgr = np.ascontiguousarray(frame_bgr)

        slot_id = shared_store.acquire(block=self._drop_policy == DropPolicy.block)
        if slot_id is None:
            if self._drop_policy == DropPolicy.drop_oldest:
                try:
                    dropped_packet = self._queue.get_nowait()
                except Empty:
                    return None
                dropped_packet.release()
                slot_id = shared_store.acquire(block=False)
            if slot_id is None:
                return None

        shared_frame = shared_store.write(slot_id, frame_bgr)
        return packet.with_frame(
            shared_frame,
            width=packet.width,
            height=packet.height,
            release=lambda slot_id=slot_id: shared_store.release(slot_id),
        )

    def _wakeup(self) -> None:
        """Signal the asyncio pipeline that a frame is available."""

        loop = self._loop
        if loop is None or loop.is_closed():
            return
        event = self._event
        if event is None:
            return
        loop.call_soon_threadsafe(event.set)

    async def get(self) -> FramePacket:
        """Await and return the next published frame packet."""

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

        removed_packets: list[FramePacket] = []
        with self._queue.mutex:
            retained_packets = type(self._queue.queue)()
            for packet in self._queue.queue:
                if packet.camera_id == camera_id:
                    removed_packets.append(packet)
                    continue
                retained_packets.append(packet)
            removed = len(removed_packets)
            self._queue.queue = retained_packets
            self._queue.unfinished_tasks = max(0, self._queue.unfinished_tasks - removed)
            if removed:
                self._queue.not_full.notify_all()
        for packet in removed_packets:
            packet.release()
        return len(removed_packets)

    def close(self) -> None:
        """Release queued packets and clean up shared-memory resources."""

        queued_packets: list[FramePacket] = []
        with self._queue.mutex:
            while self._queue.queue:
                queued_packets.append(self._queue.queue.popleft())
            self._queue.unfinished_tasks = 0
            self._queue.not_full.notify_all()
        for packet in queued_packets:
            packet.release()
        if self._shared_store is not None:
            self._shared_store.close()
            self._shared_store = None
