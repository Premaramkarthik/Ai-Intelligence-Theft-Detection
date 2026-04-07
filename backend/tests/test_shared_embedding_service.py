"""Tests for SharedEmbeddingService: single embed, cross-worker batching, stop()."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.services.tracking.reid.shared_embedding_service import SharedEmbeddingService


def _make_embedder(embed_dim: int = 128) -> MagicMock:
    """Return a mock embedder whose embed() returns one zero-vector per crop."""
    embedder = MagicMock()
    embedder.embed.side_effect = lambda crops: [np.zeros(embed_dim) for _ in crops]
    return embedder


def _crop() -> np.ndarray:
    return np.zeros((64, 32, 3), dtype=np.uint8)


async def test_single_embed_returns_correct_number_of_embeddings() -> None:
    embedder = _make_embedder()
    service = SharedEmbeddingService(embedder)
    await service.start()
    run_task = asyncio.create_task(service.run())

    result = await service.embed_async([_crop(), _crop()])

    assert len(result) == 2
    assert all(isinstance(e, np.ndarray) for e in result)

    service.stop()
    await asyncio.wait_for(run_task, timeout=1.0)


async def test_two_concurrent_embeds_coalesced_into_one_embedder_call() -> None:
    """embed_async called twice concurrently must produce exactly one embedder.embed() call."""
    embedder = _make_embedder()
    service = SharedEmbeddingService(embedder)
    await service.start()
    run_task = asyncio.create_task(service.run())

    # Both embed_async calls are enqueued before run() drains the queue.
    results = await asyncio.gather(
        service.embed_async([_crop()]),
        service.embed_async([_crop()]),
    )

    assert embedder.embed.call_count == 1
    combined_crops = embedder.embed.call_args[0][0]
    assert len(combined_crops) == 2  # both crops batched in one forward pass
    assert len(results[0]) == 1
    assert len(results[1]) == 1

    service.stop()
    await asyncio.wait_for(run_task, timeout=1.0)


async def test_three_concurrent_submitters_trigger_single_embedder_call() -> None:
    embedder = _make_embedder()
    service = SharedEmbeddingService(embedder)
    await service.start()
    run_task = asyncio.create_task(service.run())

    await asyncio.gather(
        service.embed_async([_crop()]),
        service.embed_async([_crop()]),
        service.embed_async([_crop()]),
    )

    assert embedder.embed.call_count == 1
    assert len(embedder.embed.call_args[0][0]) == 3

    service.stop()
    await asyncio.wait_for(run_task, timeout=1.0)


async def test_empty_crops_return_empty_without_calling_embedder() -> None:
    embedder = _make_embedder()
    service = SharedEmbeddingService(embedder)
    await service.start()
    run_task = asyncio.create_task(service.run())

    result = await service.embed_async([])

    assert result == []
    embedder.embed.assert_not_called()

    service.stop()
    await asyncio.wait_for(run_task, timeout=1.0)


async def test_stop_causes_run_to_exit_cleanly() -> None:
    embedder = _make_embedder()
    service = SharedEmbeddingService(embedder)
    await service.start()
    run_task = asyncio.create_task(service.run())

    await asyncio.sleep(0)  # let run() enter its wait loop
    service.stop()

    # run() polls with a 0.5s timeout; it must exit within 1s.
    await asyncio.wait_for(run_task, timeout=1.0)
    assert run_task.done()
