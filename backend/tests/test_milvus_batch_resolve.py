"""Tests for MilvusIdentityStore: batch_resolve single search round-trip, semaphore cap, resolve_identity."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, call

import numpy as np
import pytest

from src.services.tracking.identity.milvus_store import (
    BatchResolveRequest,
    MilvusIdentityStore,
)


def _make_store(similarity_threshold: float = 0.8) -> MilvusIdentityStore:
    return MilvusIdentityStore(
        uri="http://localhost:19530",
        collection_name="test_identities",
        embedding_dimension=4,
        timeout_seconds=5.0,
        similarity_threshold=similarity_threshold,
        search_limit=1,
    )


def _make_mock_client(
    search_results: list[list[dict]] | None = None,
) -> MagicMock:
    """Build a MilvusClient mock that skips collection setup."""
    client = MagicMock()
    client.has_collection.return_value = True
    client.search.return_value = search_results or []
    client.upsert.return_value = None
    client.get.return_value = []
    return client


def _embedding(dim: int = 4) -> np.ndarray:
    v = np.ones(dim, dtype=np.float32)
    return v / np.linalg.norm(v)


def _make_request(track_id: str = "t1") -> BatchResolveRequest:
    return BatchResolveRequest(
        camera_id="cam1",
        stream_name="cam1",
        local_track_id=track_id,
        embedding=_embedding(),
    )


# ---------------------------------------------------------------------------
# batch_resolve — single search round-trip
# ---------------------------------------------------------------------------


async def test_batch_resolve_issues_exactly_one_search_call_for_n_requests() -> None:
    store = _make_store()
    client = _make_mock_client(search_results=[[], [], []])
    store._client = client

    requests = [_make_request(f"t{i}") for i in range(3)]
    results = await store.batch_resolve(requests)

    client.search.assert_called_once()
    # All 3 vectors sent in one call.
    vectors_sent = client.search.call_args.kwargs.get(
        "data", client.search.call_args[0][0] if client.search.call_args[0] else []
    )
    assert len(vectors_sent) == 3
    assert len(results) == 3


async def test_batch_resolve_empty_requests_returns_empty_list() -> None:
    store = _make_store()
    client = _make_mock_client()
    store._client = client

    results = await store.batch_resolve([])

    client.search.assert_not_called()
    assert results == []


# ---------------------------------------------------------------------------
# semaphore cap
# ---------------------------------------------------------------------------


async def test_batch_resolve_semaphore_initialized_to_max_concurrent() -> None:
    """After a complete batch_resolve the semaphore value equals max_concurrent."""
    store = _make_store()
    client = _make_mock_client(search_results=[[]])
    store._client = client

    await store.batch_resolve([_make_request()], max_concurrent=3)

    assert store._batch_semaphore is not None
    assert store._batch_semaphore._value == 3  # fully released after completion


async def test_batch_resolve_semaphore_created_lazily_on_first_call() -> None:
    store = _make_store()
    assert store._batch_semaphore is None

    client = _make_mock_client(search_results=[[]])
    store._client = client
    await store.batch_resolve([_make_request()])

    assert store._batch_semaphore is not None


# ---------------------------------------------------------------------------
# resolve_identity — above-threshold → matched_existing=True
# ---------------------------------------------------------------------------


def test_resolve_identity_matched_existing_true_when_similarity_above_threshold() -> None:
    store = _make_store(similarity_threshold=0.8)
    client = _make_mock_client(
        search_results=[[{"id": "person_existing_abc", "distance": 0.95}]]
    )
    store._client = client

    match = store.resolve_identity(
        camera_id="cam1",
        stream_name="cam1",
        local_track_id="t1",
        embedding=_embedding(),
    )

    assert match.matched_existing is True
    assert match.identity_id == "person_existing_abc"
    assert match.similarity == pytest.approx(0.95)


def test_resolve_identity_matched_existing_false_when_similarity_below_threshold() -> None:
    store = _make_store(similarity_threshold=0.8)
    client = _make_mock_client(
        search_results=[[{"id": "person_existing_abc", "distance": 0.5}]]
    )
    store._client = client

    match = store.resolve_identity(
        camera_id="cam1",
        stream_name="cam1",
        local_track_id="t1",
        embedding=_embedding(),
    )

    assert match.matched_existing is False
    assert match.identity_id.startswith("person_")
