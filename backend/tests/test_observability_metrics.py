"""Tests for Prometheus metric recording and runtime collectors."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from prometheus_client import CollectorRegistry
from src.observability.http_middleware import HttpMetricsMiddleware
from src.observability.metrics import PrometheusMetrics
from src.observability.runtime_metrics import (
    RuntimeMetricsCollector,
    RuntimeMetricsDependencies,
)
from src.observability.system_metrics import SystemMetricsCollector
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route


class SimpleQueue:
    def __init__(self) -> None:
        self._items: list[object] = []

    async def publish(self, item: object) -> None:
        self._items.append(item)

    def qsize(self) -> int:
        return len(self._items)


def _sample_value(families: dict[str, object], family_name: str, sample_name: str) -> float:
    family = families[family_name]
    return next(sample.value for sample in family.samples if sample.name == sample_name)


# pylint: disable=too-many-statements
def test_prometheus_metrics_record_camera_and_backend_values() -> None:
    """Record realtime, websocket, HTTP, and dependency metrics."""

    registry = CollectorRegistry()
    metrics = PrometheusMetrics(registry=registry)

    metrics.record_frame_received("cam_1")
    metrics.record_frame_dropped("cam_1")
    metrics.increment_stream_decoded_frames("cam_1", 3)
    metrics.observe_frame_processing_latency("cam_1", 12.5)
    metrics.set_stream_worker_count(1)
    metrics.set_stream_worker_up("cam_1", True)
    metrics.set_stream_reconnect_attempts("cam_1", 2)
    metrics.set_stream_current_fps("cam_1", 5.0)
    metrics.set_stream_queue_latency_ms("cam_1", 7.5)
    metrics.set_stream_decode_time_ms("cam_1", 3.2)
    metrics.set_stream_last_frame_age_seconds("cam_1", 0.9)
    metrics.set_tracking_worker_count(1)
    metrics.set_tracking_worker_up("cam_1", True)
    metrics.increment_tracking_processed_frames("cam_1", 4)
    metrics.increment_tracking_published_frames("cam_1", 2)
    metrics.set_tracking_active_tracks("cam_1", 3)
    metrics.observe_tracking_identity_lookup_duration("cam_1", 0.02)
    metrics.increment_tracking_identity_resolution("cam_1", matched_existing=True)
    metrics.set_queue_size(7)
    metrics.set_system_cpu_usage_percent(48.5)
    metrics.set_process_cpu_usage_percent(12.0)
    metrics.set_system_memory_usage_bytes(1024)
    metrics.set_process_memory_usage_bytes(2048)
    metrics.increment_system_network_receive_bytes(512)
    metrics.increment_system_network_transmit_bytes(256)
    metrics.observe_http_request("/streams/{camera_id}/start", "POST", 200, 0.12)
    metrics.increment_websocket_connections()
    metrics.record_websocket_message_sent("stream.updated")
    metrics.record_websocket_broadcast_failure("stream.updated")
    metrics.set_dependency_health("mediamtx", True)
    metrics.increment_tracking_kafka_messages_published()
    metrics.increment_tracking_kafka_publish_failures()
    metrics.increment_stream_kafka_messages_consumed()
    metrics.increment_stream_kafka_consumer_failures()
    metrics.increment_inference_frame_drop("cam_1")

    families = {metric.name: metric for metric in registry.collect()}

    assert _sample_value(families, "frames_received", "frames_received_total") == 1.0
    assert _sample_value(families, "frames_dropped", "frames_dropped_total") == 1.0
    assert (
        _sample_value(
            families,
            "stream_decoded_frames",
            "stream_decoded_frames_total",
        )
        == 3.0
    )
    assert families["stream_worker_count"].samples[0].value == 1.0
    assert (
        _sample_value(
            families,
            "tracking_processed_frames",
            "tracking_processed_frames_total",
        )
        == 4.0
    )
    assert families["queue_size"].samples[0].value == 7.0
    assert (
        _sample_value(
            families,
            "backend_http_requests",
            "backend_http_requests_total",
        )
        == 1.0
    )
    assert families["backend_websocket_connections_current"].samples[0].value == 1.0
    assert families["backend_dependency_health"].samples[0].value == 1.0
    assert (
        _sample_value(
            families,
            "tracking_kafka_messages_published",
            "tracking_kafka_messages_published_total",
        )
        == 1.0
    )
    assert (
        _sample_value(
            families,
            "stream_kafka_messages_consumed",
            "stream_kafka_messages_consumed_total",
        )
        == 1.0
    )
    assert (
        _sample_value(
            families,
            "inference_frame_drops",
            "inference_frame_drops_total",
        )
        == 1.0
    )


async def test_system_metrics_collector_updates_queue_and_resource_metrics(
    monkeypatch,
) -> None:
    """Publish psutil-derived metrics into Prometheus without blocking the event loop."""

    registry = CollectorRegistry()
    metrics = PrometheusMetrics(registry=registry)
    frame_queue = SimpleQueue()
    await frame_queue.publish(
        SimpleNamespace(camera_id="cam_1", stream_name="cam_1", sequence_number=1),
    )

    process_info = SimpleNamespace(rss=4096)

    class FakeProcess:
        """Return deterministic process-level psutil values for tests."""

        def cpu_percent(self, interval=None) -> float:
            del interval
            return 21.0

        def memory_info(self) -> SimpleNamespace:
            return process_info

    def fake_process_factory() -> FakeProcess:
        return FakeProcess()

    def fake_cpu_percent(interval=None) -> float:
        del interval
        return 37.5

    def fake_virtual_memory() -> SimpleNamespace:
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
        return next(network_samples)

    monkeypatch.setattr(
        "src.observability.system_metrics.psutil.net_io_counters",
        next_network_sample,
    )

    async def immediate_to_thread(function, *args, **kwargs):
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


async def test_runtime_metrics_collector_exports_worker_and_dependency_state() -> None:
    """Collect runtime metrics from worker managers using stable snapshot doubles."""

    registry = CollectorRegistry()
    metrics = PrometheusMetrics(registry=registry)
    now = datetime.now(timezone.utc)

    class FakeStreamManager:
        def active_cameras(self) -> list[str]:
            return ["cam_1"]

        def active_worker_count(self) -> int:
            return 1

        def get_snapshot(self, camera_id: str) -> SimpleNamespace:
            assert camera_id == "cam_1"
            return SimpleNamespace(
                desired_state=SimpleNamespace(value="running"),
                is_registered=True,
                is_process_alive=True,
                process_id=None,
                restart_count=0,
                reconnect_attempts=1,
                decoded_frames=8,
                sampled_frames=4,
                dropped_frames=1,
                current_fps=5.0,
                queue_latency_ms=6.0,
                decode_time_ms=3.5,
                last_frame_at=now - timedelta(seconds=2),
            )

    class FakeTrackingManager:
        def active_cameras(self) -> list[str]:
            return ["cam_1"]

        def active_worker_count(self) -> int:
            return 1

        def get_runtime_snapshot(self, camera_id: str) -> SimpleNamespace:
            assert camera_id == "cam_1"
            return SimpleNamespace(
                is_registered=True,
                is_process_alive=True,
                reconnect_attempts=0,
                processed_frames=10,
                published_frames=6,
                active_tracks=2,
                last_frame_at=now - timedelta(seconds=1),
            )

    collector = RuntimeMetricsCollector(
        metrics=metrics,
        dependencies=RuntimeMetricsDependencies(
            stream_manager=FakeStreamManager(),
            tracking_manager=FakeTrackingManager(),
            tracking_kafka_producer=SimpleNamespace(
                health_snapshot=lambda: {"healthy": True, "last_error": None},
            ),
            kafka_consumer=SimpleNamespace(
                health_snapshot=lambda: {"healthy": False, "last_error": "boom"},
            ),
            mediamtx_service=SimpleNamespace(
                health_snapshot=lambda: SimpleNamespace(healthy=True),
            ),
        ),
        interval_seconds=60.0,
    )

    await collector.collect_once()

    families = {metric.name: metric for metric in registry.collect()}

    assert families["stream_worker_count"].samples[0].value == 1.0
    assert families["stream_worker_up"].samples[0].value == 1.0
    assert families["stream_decoded_frames"].samples[0].value == 8.0
    assert families["tracking_worker_count"].samples[0].value == 1.0
    assert families["tracking_processed_frames"].samples[0].value == 10.0
    assert families["tracking_active_tracks"].samples[0].value == 2.0

    dependency_samples = {
        sample.labels["component"]: sample.value
        for sample in families["backend_dependency_health"].samples
        if sample.name == "backend_dependency_health"
    }
    assert dependency_samples["mediamtx"] == 1.0
    assert dependency_samples["kafka_consumer"] == 0.0
    assert dependency_samples["tracking_kafka_producer"] == 1.0


async def test_http_metrics_middleware_records_route_templates() -> None:
    """Record HTTP metrics using the templated FastAPI route instead of the raw path."""

    registry = CollectorRegistry()
    metrics = PrometheusMetrics(registry=registry)
    app = FastAPI()
    app.state.metrics_recorder = metrics
    middleware = HttpMetricsMiddleware(app)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/streams/cam_1/info",
            "headers": [],
            "query_string": b"",
            "app": app,
            "route": Route("/streams/{camera_id}/info", endpoint=lambda: None),
        },
    )

    async def call_next(_request: Request) -> Response:
        return Response(status_code=200)

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200
    families = {metric.name: metric for metric in registry.collect()}
    request_samples = [
        sample
        for sample in families["backend_http_requests"].samples
        if sample.name == "backend_http_requests_total"
    ]
    assert request_samples[0].labels["route"] == "/streams/{camera_id}/info"
