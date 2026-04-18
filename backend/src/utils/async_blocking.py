"""Helpers for running blocking callables without blocking the asyncio loop."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from queue import Empty, Queue
from threading import Thread
from typing import TypeVar


T = TypeVar("T")


async def run_blocking_in_daemon_thread(
    function: Callable[..., T],
    *args: object,
    poll_interval_seconds: float = 0.001,
    **kwargs: object,
) -> T:
    """Run a blocking callable in a daemon thread and await its result."""

    result_queue: Queue[tuple[bool, object]] = Queue(maxsize=1)

    def _target() -> None:
        try:
            result_queue.put((True, function(*args, **kwargs)))
        except BaseException as exc:  # pylint: disable=broad-except
            result_queue.put((False, exc))

    Thread(target=_target, name="async-blocking-worker", daemon=True).start()
    while True:
        try:
            success, payload = result_queue.get_nowait()
        except Empty:
            await asyncio.sleep(poll_interval_seconds)
            continue
        if success:
            return payload  # type: ignore[return-value]
        raise payload  # type: ignore[misc]
