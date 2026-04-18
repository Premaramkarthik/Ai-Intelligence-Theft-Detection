"""Asynchronous psutil-based system metric collection for Prometheus."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

import psutil

from src.observability.metrics import MetricsRecorder
from src.utils.async_blocking import run_blocking_in_daemon_thread


class QueueDepthProvider(Protocol):
    """Structural protocol for queue-like objects that expose ``qsize()``."""

    def qsize(self) -> int:
        """Return the current queue depth."""


@dataclass(slots=True)
class SystemMetricsSnapshot:
    """Represent one lightweight system metrics sample."""

    system_cpu_usage_percent: float
    process_cpu_usage_percent: float
    system_memory_usage_bytes: int
    process_memory_usage_bytes: int
    system_network_receive_bytes: int
    system_network_transmit_bytes: int


class SystemMetricsCollector:
    """Collect host and process metrics in a non-blocking background task."""

    def __init__(
        self,
        metrics: MetricsRecorder,
        frame_queue: QueueDepthProvider | None = None,
        interval_seconds: float = 5.0,
    ) -> None:
        """Create a collector bound to the shared frame queue and metrics recorder."""

        self._metrics = metrics
        self._frame_queue = frame_queue
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._process = psutil.Process()
        self._previous_network_snapshot: tuple[int, int] | None = None
        psutil.cpu_percent(interval=None)
        self._process.cpu_percent(interval=None)

    async def start(self) -> None:
        """Start the periodic metrics collection task if it is not already running."""

        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Cancel the periodic metrics collection task."""

        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def collect_once(self) -> None:
        """Collect and publish one metrics snapshot without blocking the event loop."""

        snapshot = await run_blocking_in_daemon_thread(self._sample_snapshot)
        queue_size = self._frame_queue.qsize() if self._frame_queue is not None else 0
        self._metrics.set_queue_size(queue_size)
        self._metrics.set_system_cpu_usage_percent(snapshot.system_cpu_usage_percent)
        self._metrics.set_process_cpu_usage_percent(snapshot.process_cpu_usage_percent)
        self._metrics.set_system_memory_usage_bytes(snapshot.system_memory_usage_bytes)
        self._metrics.set_process_memory_usage_bytes(snapshot.process_memory_usage_bytes)
        self._update_network_counters(snapshot)

    async def _run_loop(self) -> None:
        """Collect system metrics forever until the collector is stopped."""

        while True:
            await self.collect_once()
            await asyncio.sleep(self._interval_seconds)

    def _sample_snapshot(self) -> SystemMetricsSnapshot:
        """Read CPU, memory, and network metrics from psutil."""

        network_counters = psutil.net_io_counters()
        return SystemMetricsSnapshot(
            system_cpu_usage_percent=psutil.cpu_percent(interval=None),
            process_cpu_usage_percent=self._process.cpu_percent(interval=None),
            system_memory_usage_bytes=psutil.virtual_memory().used,
            process_memory_usage_bytes=self._process.memory_info().rss,
            system_network_receive_bytes=network_counters.bytes_recv,
            system_network_transmit_bytes=network_counters.bytes_sent,
        )

    def _update_network_counters(self, snapshot: SystemMetricsSnapshot) -> None:
        """Convert cumulative psutil byte counts into Prometheus counter increments."""

        current_snapshot = (
            snapshot.system_network_receive_bytes,
            snapshot.system_network_transmit_bytes,
        )
        if self._previous_network_snapshot is None:
            self._previous_network_snapshot = current_snapshot
            return

        previous_receive, previous_transmit = self._previous_network_snapshot
        receive_delta = max(snapshot.system_network_receive_bytes - previous_receive, 0)
        transmit_delta = max(snapshot.system_network_transmit_bytes - previous_transmit, 0)
        self._metrics.increment_system_network_receive_bytes(receive_delta)
        self._metrics.increment_system_network_transmit_bytes(transmit_delta)
        self._previous_network_snapshot = current_snapshot
