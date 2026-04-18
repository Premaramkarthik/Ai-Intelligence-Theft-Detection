"""Singleton re-ID embedding service shared across all tracking workers."""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import TYPE_CHECKING

import numpy as np

from src.services.tracking.reid.embedder import TrackingReIdEmbedder
from src.utils.async_blocking import run_blocking_in_daemon_thread

if TYPE_CHECKING:
    pass


class SharedEmbeddingService:
    """One TrackingReIdEmbedder instance shared across all workers.

    Workers submit batches of image crops via an asyncio.Queue; a single
    background asyncio task drains the queue, coalesces pending items into
    one batched forward pass, and resolves each caller's Future.
    """

    def __init__(self, embedder: TrackingReIdEmbedder) -> None:
        self._embedder = embedder
        self._queue: asyncio.Queue[
            tuple[list[np.ndarray], asyncio.Future[list[np.ndarray]]]
        ] | None = None
        self._stopped = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialise the internal queue (must be called from async context)."""
        self._queue = asyncio.Queue()
        self._stopped = False

    def stop(self) -> None:
        """Signal the background task to exit on its next iteration."""
        self._stopped = True

    async def run(self) -> None:
        """Background task: batch-embed crops submitted by tracking workers."""
        assert self._queue is not None, "Call start() before run()."
        while not self._stopped:
            # Wait for the first item with a timeout so stop() is respected.
            try:
                first_crops, first_future = await asyncio.wait_for(
                    self._queue.get(), timeout=0.5
                )
            except asyncio.TimeoutError:
                continue

            # Drain any additional items already in the queue for free batching.
            pending: list[tuple[list[np.ndarray], asyncio.Future[list[np.ndarray]]]] = [
                (first_crops, first_future)
            ]
            while True:
                try:
                    pending.append(self._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

            # Build one concatenated crop list and record per-request slice bounds.
            all_crops: list[np.ndarray] = []
            offsets: list[int] = [0]
            for crops, _ in pending:
                all_crops.extend(crops)
                offsets.append(len(all_crops))

            # Run the forward pass (CPU/GPU blocking call) in a thread so the
            # event loop remains responsive to other coroutines.
            try:
                all_embeddings: list[np.ndarray] = await run_blocking_in_daemon_thread(
                    self._embedder.embed, all_crops
                )
            except Exception as exc:  # pylint: disable=broad-except
                for _, future in pending:
                    if not future.done():
                        future.set_exception(exc)
                continue

            # Distribute results back to each caller.
            for i, (_, future) in enumerate(pending):
                if not future.done():
                    future.set_result(all_embeddings[offsets[i] : offsets[i + 1]])

    # ------------------------------------------------------------------
    # Embedding API
    # ------------------------------------------------------------------

    async def embed_async(self, crops: list[np.ndarray]) -> list[np.ndarray]:
        """Submit crops and await results from async code."""
        if not crops:
            return []
        assert self._queue is not None, "Call start() before embed_async()."
        loop = asyncio.get_running_loop()
        future: asyncio.Future[list[np.ndarray]] = loop.create_future()
        await self._queue.put((crops, future))
        return await future

    def embed_from_thread(
        self,
        crops: list[np.ndarray],
        loop: asyncio.AbstractEventLoop,
    ) -> list[np.ndarray]:
        """Submit crops from a worker thread and block until the result arrives.

        Uses run_coroutine_threadsafe so the submission is dispatched through
        the event loop that owns the queue.
        """
        if not crops:
            return []
        cf_future: concurrent.futures.Future[list[np.ndarray]] = (
            asyncio.run_coroutine_threadsafe(self.embed_async(crops), loop)
        )
        return cf_future.result(timeout=30.0)
