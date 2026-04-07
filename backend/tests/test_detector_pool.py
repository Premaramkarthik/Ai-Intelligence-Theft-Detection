"""Tests for DetectorPool: context-manager checkout, concurrent blocking, manual get/put, available()."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from src.services.tracking.contracts import PersonDetector
from src.services.tracking.detectors.detector_pool import DetectorPool


def _make_detector() -> PersonDetector:
    return MagicMock(spec=PersonDetector)


def test_detector_pool_raises_on_empty_list() -> None:
    with pytest.raises(ValueError, match="at least one detector"):
        DetectorPool([])


def test_detector_pool_size_reflects_initial_count() -> None:
    pool = DetectorPool([_make_detector(), _make_detector()])
    assert pool.size() == 2


async def test_context_manager_yields_detector_and_returns_it_on_exit() -> None:
    detector = _make_detector()
    pool = DetectorPool([detector])

    assert pool.available() == 1
    async with pool.acquire() as checked_out:
        assert checked_out is detector
        assert pool.available() == 0
    assert pool.available() == 1


async def test_acquire_blocks_when_pool_exhausted() -> None:
    """get() must time out when the only detector is already checked out."""
    pool = DetectorPool([_make_detector()])

    d = await pool.get()
    assert pool.available() == 0

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(pool.get(), timeout=0.05)

    # Cleanup — return the detector so the pool is clean.
    pool.put(d)


async def test_manual_get_put_available_cycle() -> None:
    detector = _make_detector()
    pool = DetectorPool([detector])

    assert pool.available() == 1
    checked = await pool.get()
    assert checked is detector
    assert pool.available() == 0

    pool.put(checked)
    assert pool.available() == 1


async def test_put_after_worker_exit_re_releases_slot() -> None:
    """After a manual get(), calling put() must unblock a waiting get()."""
    pool = DetectorPool([_make_detector()])

    d = await pool.get()
    assert pool.available() == 0

    pool.put(d)
    assert pool.available() == 1

    # Semaphore must be free again — second get() must not block.
    d2 = await asyncio.wait_for(pool.get(), timeout=0.1)
    assert d2 is d
    pool.put(d2)
