"""Prometheus metric definitions for the realtime video pipeline."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class MetricsRecorder:
    """Define the metric operations used by the realtime pipeline."""

    def record_frame_received(self, camera_id: str) -> None:
        """Record that a sampled frame entered the application pipeline."""

        del camera_id

    def record_frame_dropped(self, camera_id: str) -> None:
        """Record that a sampled frame was dropped before downstream processing."""

        del camera_id

    def observe_frame_processing_latency(self, camera_id: str, latency_ms: float) -> None:
        """Observe frame processing latency in milliseconds for one camera."""

        del camera_id, latency_ms

    def set_queue_size(self, size: int) -> None:
        """Set the shared realtime frame queue size gauge."""

        del size

    def set_system_cpu_usage_percent(self, usage_percent: float) -> None:
        """Set the system-wide CPU usage gauge."""

        del usage_percent

    def set_process_cpu_usage_percent(self, usage_percent: float) -> None:
        """Set the backend process CPU usage gauge."""

        del usage_percent

    def set_system_memory_usage_bytes(self, memory_bytes: int) -> None:
        """Set the system memory usage gauge."""

        del memory_bytes

    def set_process_memory_usage_bytes(self, memory_bytes: int) -> None:
        """Set the backend process RSS memory gauge."""

        del memory_bytes

    def increment_system_network_receive_bytes(self, byte_count: int) -> None:
        """Increment the received network byte counter."""

        del byte_count

    def increment_system_network_transmit_bytes(self, byte_count: int) -> None:
        """Increment the transmitted network byte counter."""

        del byte_count


class NullMetricsRecorder(MetricsRecorder):
    """Provide a no-op metrics recorder when observability is disabled."""

    def record_frame_received(self, camera_id: str) -> None:
        """Ignore frame-received events when metrics are disabled."""

        del camera_id

    def record_frame_dropped(self, camera_id: str) -> None:
        """Ignore frame-drop events when metrics are disabled."""

        del camera_id

    def observe_frame_processing_latency(self, camera_id: str, latency_ms: float) -> None:
        """Ignore latency observations when metrics are disabled."""

        del camera_id, latency_ms

    def set_queue_size(self, size: int) -> None:
        """Ignore queue-size updates when metrics are disabled."""

        del size

    def set_system_cpu_usage_percent(self, usage_percent: float) -> None:
        """Ignore system CPU updates when metrics are disabled."""

        del usage_percent

    def set_process_cpu_usage_percent(self, usage_percent: float) -> None:
        """Ignore process CPU updates when metrics are disabled."""

        del usage_percent

    def set_system_memory_usage_bytes(self, memory_bytes: int) -> None:
        """Ignore system memory updates when metrics are disabled."""

        del memory_bytes

    def set_process_memory_usage_bytes(self, memory_bytes: int) -> None:
        """Ignore process memory updates when metrics are disabled."""

        del memory_bytes

    def increment_system_network_receive_bytes(self, byte_count: int) -> None:
        """Ignore received network byte updates when metrics are disabled."""

        del byte_count

    def increment_system_network_transmit_bytes(self, byte_count: int) -> None:
        """Ignore transmitted network byte updates when metrics are disabled."""

        del byte_count


class PrometheusMetrics(MetricsRecorder):
    """Own Prometheus counters, gauges, and histograms for the backend."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        """Create the Prometheus metrics registry and all metric families."""

        self._registry = registry or CollectorRegistry()
        self._frames_received_total = Counter(
            "frames_received_total",
            "Sampled frames received by the realtime pipeline.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._frames_dropped_total = Counter(
            "frames_dropped_total",
            "Sampled frames dropped because of downstream backpressure.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._frame_processing_latency_ms = Histogram(
            "frame_processing_latency_ms",
            "Per-frame processing latency observed in the PyAV worker.",
            labelnames=("camera_id",),
            buckets=(1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0),
            registry=self._registry,
        )
        self._queue_size = Gauge(
            "queue_size",
            "Current number of sampled frames buffered in the shared queue.",
            registry=self._registry,
        )
        self._system_cpu_usage_percent = Gauge(
            "system_cpu_usage_percent",
            "System-wide CPU utilization percentage.",
            registry=self._registry,
        )
        self._process_cpu_usage_percent = Gauge(
            "process_cpu_usage_percent",
            "CPU utilization percentage of the backend process.",
            registry=self._registry,
        )
        self._system_memory_usage_bytes = Gauge(
            "system_memory_usage_bytes",
            "System memory currently used in bytes.",
            registry=self._registry,
        )
        self._process_memory_usage_bytes = Gauge(
            "process_memory_usage_bytes",
            "Resident set size of the backend process in bytes.",
            registry=self._registry,
        )
        self._system_network_receive_bytes_total = Counter(
            "system_network_receive_bytes_total",
            "Network bytes received by the host since collector start.",
            registry=self._registry,
        )
        self._system_network_transmit_bytes_total = Counter(
            "system_network_transmit_bytes_total",
            "Network bytes transmitted by the host since collector start.",
            registry=self._registry,
        )

    @property
    def registry(self) -> CollectorRegistry:
        """Return the Prometheus registry used by this metrics recorder."""

        return self._registry

    def record_frame_received(self, camera_id: str) -> None:
        """Increment the per-camera sampled frame counter."""

        self._frames_received_total.labels(camera_id=camera_id).inc()

    def record_frame_dropped(self, camera_id: str) -> None:
        """Increment the per-camera dropped frame counter."""

        self._frames_dropped_total.labels(camera_id=camera_id).inc()

    def observe_frame_processing_latency(self, camera_id: str, latency_ms: float) -> None:
        """Observe per-camera frame processing latency in milliseconds."""

        self._frame_processing_latency_ms.labels(camera_id=camera_id).observe(latency_ms)

    def set_queue_size(self, size: int) -> None:
        """Update the current shared queue size gauge."""

        self._queue_size.set(size)

    def set_system_cpu_usage_percent(self, usage_percent: float) -> None:
        """Update the system CPU usage gauge."""

        self._system_cpu_usage_percent.set(usage_percent)

    def set_process_cpu_usage_percent(self, usage_percent: float) -> None:
        """Update the backend process CPU usage gauge."""

        self._process_cpu_usage_percent.set(usage_percent)

    def set_system_memory_usage_bytes(self, memory_bytes: int) -> None:
        """Update the system memory usage gauge."""

        self._system_memory_usage_bytes.set(memory_bytes)

    def set_process_memory_usage_bytes(self, memory_bytes: int) -> None:
        """Update the backend process RSS memory gauge."""

        self._process_memory_usage_bytes.set(memory_bytes)

    def increment_system_network_receive_bytes(self, byte_count: int) -> None:
        """Increment the cumulative received network byte counter."""

        if byte_count > 0:
            self._system_network_receive_bytes_total.inc(byte_count)

    def increment_system_network_transmit_bytes(self, byte_count: int) -> None:
        """Increment the cumulative transmitted network byte counter."""

        if byte_count > 0:
            self._system_network_transmit_bytes_total.inc(byte_count)
