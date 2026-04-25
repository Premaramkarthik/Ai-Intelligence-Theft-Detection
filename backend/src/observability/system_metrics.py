"""Periodic host/process metrics collection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import psutil

from src.observability.metrics import NullMetricsRecorder, PrometheusMetrics


@dataclass(slots=True)
class _NetworkSample:
    bytes_recv: int
    bytes_sent: int


@dataclass(slots=True)
class _DiskSample:
    read_bytes: int
    write_bytes: int


class SystemMetricsCollector:
    """Sample host/process resource usage without blocking the event loop."""

    def __init__(
        self,
        *,
        metrics: PrometheusMetrics | NullMetricsRecorder,
        frame_queue,
        interval_seconds: float = 5.0,
    ) -> None:
        self._metrics = metrics
        self._frame_queue = frame_queue
        self._interval_seconds = max(interval_seconds, 0.5)
        self._task: asyncio.Task[None] | None = None
        self._previous_network: _NetworkSample | None = None
        self._previous_disk: _DiskSample | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def collect_once(self) -> None:
        self._metrics.set_queue_size(int(self._frame_queue.qsize()))

        process = await asyncio.to_thread(psutil.Process)
        system_cpu = await asyncio.to_thread(psutil.cpu_percent, None)
        process_cpu = await asyncio.to_thread(process.cpu_percent, None)
        virtual_memory = await asyncio.to_thread(psutil.virtual_memory)
        process_memory = await asyncio.to_thread(process.memory_info)

        self._metrics.set_system_cpu_usage_percent(float(system_cpu))
        self._metrics.set_process_cpu_usage_percent(float(process_cpu))
        self._metrics.set_system_memory_usage_bytes(float(virtual_memory.used))
        self._metrics.set_process_memory_usage_bytes(float(process_memory.rss))

        network = await asyncio.to_thread(psutil.net_io_counters)
        current_network = _NetworkSample(
            bytes_recv=int(network.bytes_recv),
            bytes_sent=int(network.bytes_sent),
        )
        if self._previous_network is not None:
            self._metrics.increment_system_network_receive_bytes(
                max(0, current_network.bytes_recv - self._previous_network.bytes_recv)
            )
            self._metrics.increment_system_network_transmit_bytes(
                max(0, current_network.bytes_sent - self._previous_network.bytes_sent)
            )
        self._previous_network = current_network

        disk = await asyncio.to_thread(_safe_disk_io_counters)
        current_disk = _DiskSample(
            read_bytes=int(disk.read_bytes),
            write_bytes=int(disk.write_bytes),
        )
        if self._previous_disk is not None:
            self._metrics.increment_system_disk_read_bytes(
                max(0, current_disk.read_bytes - self._previous_disk.read_bytes)
            )
            self._metrics.increment_system_disk_write_bytes(
                max(0, current_disk.write_bytes - self._previous_disk.write_bytes)
            )
        self._previous_disk = current_disk

    async def _run(self) -> None:
        while True:
            await self.collect_once()
            await asyncio.sleep(self._interval_seconds)


def _safe_disk_io_counters():
    sample = psutil.disk_io_counters()
    if sample is None:
        return SimpleNamespace(read_bytes=0, write_bytes=0)
    return sample
