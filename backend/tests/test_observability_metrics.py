"""Tests for Prometheus metrics recording and psutil-based collectors."""

from __future__ import annotations

from types import SimpleNamespace

from prometheus_client import CollectorRegistry
from src.observability.metrics import PrometheusMetrics
from src.observability.system_metrics import SystemMetricsCollector
from src.services.realtime_video.queue import FrameQueue


def test_prometheus_metrics_record_camera_and_system_values() -> None:
    """Record frame and system metrics into an isolated Prometheus registry."""

    registry = CollectorRegistry()
    metrics = PrometheusMetrics(registry=registry)

    metrics.record_frame_received("cam_1")
    metrics.record_frame_dropped("cam_1")
    metrics.observe_frame_processing_latency("cam_1", 12.5)
    metrics.set_queue_size(7)
    metrics.set_system_cpu_usage_percent(48.5)
    metrics.set_process_cpu_usage_percent(12.0)
    metrics.set_system_memory_usage_bytes(1024)
    metrics.set_process_memory_usage_bytes(2048)
    metrics.increment_system_network_receive_bytes(512)
    metrics.increment_system_network_transmit_bytes(256)

    families = {metric.name: metric for metric in registry.collect()}

    assert families["frames_received"].samples[0].value == 1.0
    assert families["frames_dropped"].samples[0].value == 1.0
    assert families["queue_size"].samples[0].value == 7.0
    assert families["system_cpu_usage_percent"].samples[0].value == 48.5
    assert families["process_memory_usage_bytes"].samples[0].value == 2048.0
    assert families["system_network_receive_bytes"].samples[0].value == 512.0


async def test_system_metrics_collector_updates_queue_and_resource_metrics(
    monkeypatch,
) -> None:
    """Publish psutil-derived metrics into Prometheus without blocking the event loop."""

    registry = CollectorRegistry()
    metrics = PrometheusMetrics(registry=registry)
    frame_queue = FrameQueue(maxsize=4)
    await frame_queue.publish(
        SimpleNamespace(camera_id="cam_1", stream_name="cam_1", sequence_number=1),
    )

    process_info = SimpleNamespace(rss=4096)

    class FakeProcess:
        """Return deterministic process-level psutil values for tests."""

        def cpu_percent(self, interval=None) -> float:
            """Return a stable process CPU percentage value."""

            del interval
            return 21.0

        def memory_info(self) -> SimpleNamespace:
            """Return a stable process memory snapshot."""

            return process_info

    def fake_process_factory() -> FakeProcess:
        """Create a deterministic process double for psutil patching."""

        return FakeProcess()

    def fake_cpu_percent(interval=None) -> float:
        """Return a stable system CPU percentage for psutil patching."""

        del interval
        return 37.5

    def fake_virtual_memory() -> SimpleNamespace:
        """Return a stable system memory snapshot for psutil patching."""

        return SimpleNamespace(used=8192)

    monkeypatch.setattr(
        "src.observability.system_metrics.psutil.Process",
        fake_process_factory,
    )
    monkeypatch.setattr(
        "src.observability.system_metrics.psutil.cpu_percent",
        fake_cpu_percent,
    )
    monkeypatch.setattr(
        "src.observability.system_metrics.psutil.virtual_memory",
        fake_virtual_memory,
    )
    network_samples = iter(
        [
            SimpleNamespace(bytes_recv=1000, bytes_sent=2000),
            SimpleNamespace(bytes_recv=1600, bytes_sent=2600),
        ],
    )

    def next_network_sample() -> SimpleNamespace:
        """Return deterministic network counters for successive collector reads."""

        return next(network_samples)

    monkeypatch.setattr(
        "src.observability.system_metrics.psutil.net_io_counters",
        next_network_sample,
    )

    async def immediate_to_thread(function, *args, **kwargs):
        """Execute `asyncio.to_thread` work inline for deterministic tests."""

        return function(*args, **kwargs)

    monkeypatch.setattr(
        "src.observability.system_metrics.asyncio.to_thread",
        immediate_to_thread,
    )

    collector = SystemMetricsCollector(
        metrics=metrics,
        frame_queue=frame_queue,
        interval_seconds=60.0,
    )

    await collector.collect_once()
    await collector.collect_once()

    families = {metric.name: metric for metric in registry.collect()}

    assert families["queue_size"].samples[0].value == 1.0
    assert families["system_cpu_usage_percent"].samples[0].value == 37.5
    assert families["process_cpu_usage_percent"].samples[0].value == 21.0
    assert families["system_memory_usage_bytes"].samples[0].value == 8192.0
    assert families["process_memory_usage_bytes"].samples[0].value == 4096.0
    assert families["system_network_receive_bytes"].samples[0].value == 600.0
    assert families["system_network_transmit_bytes"].samples[0].value == 600.0
