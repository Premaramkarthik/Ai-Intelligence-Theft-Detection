"""Tests for RealtimeTrackingWorker enrichment loop: drain, non-blocking tracking, pending→assigned."""

from __future__ import annotations

import queue
import threading
import time
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.services.realtime_video.contracts import TrackingWorkerConfig
from src.services.tracking.contracts import PersonDetector
from src.services.tracking.identity.milvus_store import IdentityMatch, MilvusIdentityStore
from src.services.tracking.reid.shared_embedding_service import SharedEmbeddingService
from src.services.tracking.worker import (
    RealtimeTrackingWorker,
    _EnrichmentItem,
    _ENRICHMENT_QUEUE_MAXSIZE,
)


def _make_config() -> TrackingWorkerConfig:
    return TrackingWorkerConfig(
        camera_id="cam1",
        source_stream_name="cam1",
        annotated_stream_name="cam1-annotated",
        source_rtsp_url="rtsp://localhost/cam1",
        annotated_publish_rtsp_url="rtsp://localhost/cam1-annotated",
        ffmpeg_binary="ffmpeg",
        sample_fps=5.0,
        identity_sync_interval_seconds=999.0,  # disable automatic re-queuing
    )


def _make_worker(
    identity_store: MilvusIdentityStore | None = None,
    shared_embedding_service: SharedEmbeddingService | None = None,
) -> RealtimeTrackingWorker:
    if identity_store is None:
        identity_store = MagicMock(spec=MilvusIdentityStore)
    return RealtimeTrackingWorker(
        config=_make_config(),
        detector=MagicMock(spec=PersonDetector),
        identity_store=identity_store,
        shared_embedding_service=shared_embedding_service,
    )


def _crop() -> np.ndarray:
    return np.zeros((128, 64, 3), dtype=np.uint8)


def _item(track_id: str = "t1") -> _EnrichmentItem:
    return _EnrichmentItem(
        track_id=track_id,
        crop=_crop(),
        camera_id="cam1",
        stream_name="cam1",
    )


# ---------------------------------------------------------------------------
# Enrichment queue drains: items submitted are consumed
# ---------------------------------------------------------------------------


def test_enrichment_queue_drains_items_submitted_by_tracking_thread() -> None:
    """Items placed in _enrichment_queue must be consumed by _enrichment_loop."""
    identity_store = MagicMock(spec=MilvusIdentityStore)
    identity_store.resolve_identity.return_value = IdentityMatch(
        identity_id="person_abc",
        matched_existing=True,
        similarity=0.92,
    )

    embedding_svc = MagicMock(spec=SharedEmbeddingService)
    embedding_svc.embed_from_thread.return_value = [np.zeros(128)]

    worker = _make_worker(identity_store, embedding_svc)
    worker._enrichment_queue.put_nowait(_item("t1"))

    # Run the enrichment loop in a thread; stop it after the item is consumed.
    def _run() -> None:
        worker._enrichment_loop(loop=None)  # type: ignore[arg-type]

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        with worker._identities_lock:
            if "t1" in worker._persistent_identities:
                break
        time.sleep(0.01)

    worker._stop_event.set()
    t.join(timeout=3.0)

    with worker._identities_lock:
        assert "t1" in worker._persistent_identities
        state = worker._persistent_identities["t1"].state
    assert state in {"assigned", "local"}


# ---------------------------------------------------------------------------
# Enrichment queue is non-blocking (put_nowait drops on Full)
# ---------------------------------------------------------------------------


def test_enrichment_queue_put_nowait_drops_when_full() -> None:
    """Tracking must never block on a full enrichment queue."""
    worker = _make_worker()

    # Fill the queue to capacity.
    for i in range(_ENRICHMENT_QUEUE_MAXSIZE):
        worker._enrichment_queue.put_nowait(_item(f"t{i}"))

    assert worker._enrichment_queue.qsize() == _ENRICHMENT_QUEUE_MAXSIZE

    # put_nowait on a full queue must raise queue.Full immediately (not block).
    with pytest.raises(queue.Full):
        worker._enrichment_queue.put_nowait(_item("overflow"))


def test_tracking_continues_while_enrichment_queue_is_full() -> None:
    """The tracking thread uses put_nowait and must not stall on a full queue."""
    worker = _make_worker()

    for i in range(_ENRICHMENT_QUEUE_MAXSIZE):
        worker._enrichment_queue.put_nowait(_item(f"t{i}"))

    # Simulate what _track_frame does on overflow — it catches queue.Full silently.
    try:
        worker._enrichment_queue.put_nowait(_item("overflow"))
    except queue.Full:
        pass  # expected — tracking must not raise

    # Queue still at capacity, no exception propagated.
    assert worker._enrichment_queue.qsize() == _ENRICHMENT_QUEUE_MAXSIZE


# ---------------------------------------------------------------------------
# Identity state transition: pending → assigned after successful Milvus resolve
# ---------------------------------------------------------------------------


def test_identity_transitions_from_pending_to_assigned_after_successful_resolve() -> None:
    identity_store = MagicMock(spec=MilvusIdentityStore)
    identity_store.resolve_identity.return_value = IdentityMatch(
        identity_id="person_resolved",
        matched_existing=True,
        similarity=0.95,
    )

    embedding_svc = MagicMock(spec=SharedEmbeddingService)
    embedding_svc.embed_from_thread.return_value = [np.zeros(128)]

    worker = _make_worker(identity_store, embedding_svc)
    worker._enrichment_queue.put_nowait(_item("t_pending"))

    def _run() -> None:
        worker._enrichment_loop(loop=None)  # type: ignore[arg-type]

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        with worker._identities_lock:
            identity = worker._persistent_identities.get("t_pending")
            if identity is not None and identity.state == "assigned":
                break
        time.sleep(0.01)

    worker._stop_event.set()
    t.join(timeout=3.0)

    with worker._identities_lock:
        identity = worker._persistent_identities["t_pending"]

    assert identity.state == "assigned"
    assert identity.persistent_id == "person_resolved"
    assert identity.similarity == pytest.approx(0.95)
