"""Prometheus metric definitions for the realtime video backend."""

# pylint: disable=too-many-instance-attributes,too-many-public-methods

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class MetricsRecorder:
    """Define the metric operations used by the backend and runtime workers."""

    @property
    def registry(self) -> CollectorRegistry:
        """Return the Prometheus registry associated with the recorder."""

        raise NotImplementedError

    def record_frame_received(self, camera_id: str) -> None:
        """Record that a sampled frame entered the application pipeline."""

        del camera_id

    def record_frame_dropped(self, camera_id: str) -> None:
        """Record that a sampled frame was dropped before downstream processing."""

        del camera_id

    def increment_stream_decoded_frames(self, camera_id: str, frame_count: int) -> None:
        """Increment the per-camera decoded-frame counter."""

        del camera_id, frame_count

    def observe_frame_processing_latency(self, camera_id: str, latency_ms: float) -> None:
        """Observe frame processing latency in milliseconds for one camera."""

        del camera_id, latency_ms

    def set_stream_worker_count(self, worker_count: int) -> None:
        """Set the number of active realtime stream workers."""

        del worker_count

    def set_stream_worker_up(self, camera_id: str, is_up: bool) -> None:
        """Set whether a stream worker is currently active for a camera."""

        del camera_id, is_up

    def set_stream_reconnect_attempts(self, camera_id: str, attempt_count: int) -> None:
        """Set the current reconnect-attempt gauge for a stream worker."""

        del camera_id, attempt_count

    def set_stream_current_fps(self, camera_id: str, fps: float) -> None:
        """Set the current sampled FPS gauge for a stream worker."""

        del camera_id, fps

    def set_stream_queue_latency_ms(self, camera_id: str, latency_ms: float) -> None:
        """Set the latest queue latency gauge for a stream worker."""

        del camera_id, latency_ms

    def set_stream_decode_time_ms(self, camera_id: str, decode_time_ms: float) -> None:
        """Set the latest decode-time gauge for a stream worker."""

        del camera_id, decode_time_ms

    def set_stream_last_frame_age_seconds(self, camera_id: str, age_seconds: float) -> None:
        """Set the age of the most recent queued frame for a stream worker."""

        del camera_id, age_seconds

    def set_tracking_worker_count(self, worker_count: int) -> None:
        """Set the number of active tracking workers."""

        del worker_count

    def set_tracking_worker_up(self, camera_id: str, is_up: bool) -> None:
        """Set whether a tracking worker is currently active for a camera."""

        del camera_id, is_up

    def set_tracking_reconnect_attempts(self, camera_id: str, attempt_count: int) -> None:
        """Set the current reconnect-attempt gauge for a tracking worker."""

        del camera_id, attempt_count

    def increment_tracking_processed_frames(self, camera_id: str, frame_count: int) -> None:
        """Increment the processed-frame counter for a tracking worker."""

        del camera_id, frame_count

    def increment_tracking_published_frames(self, camera_id: str, frame_count: int) -> None:
        """Increment the annotated-frame publish counter for a tracking worker."""

        del camera_id, frame_count

    def set_tracking_active_tracks(self, camera_id: str, active_tracks: int) -> None:
        """Set the number of visible tracks for a camera."""

        del camera_id, active_tracks

    def set_tracking_last_frame_age_seconds(self, camera_id: str, age_seconds: float) -> None:
        """Set the age of the most recent tracking frame for a camera."""

        del camera_id, age_seconds

    def observe_tracking_identity_lookup_duration(
        self,
        camera_id: str,
        duration_seconds: float,
    ) -> None:
        """Observe Milvus identity lookup latency for one camera."""

        del camera_id, duration_seconds

    def increment_tracking_identity_resolution(
        self,
        camera_id: str,
        matched_existing: bool,
    ) -> None:
        """Increment the counter for a tracking identity resolution outcome."""

        del camera_id, matched_existing

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

    def observe_http_request(
        self,
        route: str,
        method: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Record one HTTP request against the backend control plane."""

        del route, method, status_code, duration_seconds

    def increment_websocket_connections(self) -> None:
        """Increment the active websocket connection gauge."""

    def decrement_websocket_connections(self) -> None:
        """Decrement the active websocket connection gauge."""

    def record_websocket_message_sent(self, message_type: str) -> None:
        """Record a successful websocket broadcast payload."""

        del message_type

    def record_websocket_broadcast_failure(self, message_type: str) -> None:
        """Record a websocket broadcast failure."""

        del message_type

    def set_dependency_health(self, component: str, is_healthy: bool) -> None:
        """Set a binary health gauge for an internal dependency."""

        del component, is_healthy

    def increment_tracking_kafka_messages_published(self) -> None:
        """Increment the Kafka tracking publish success counter."""

    def increment_tracking_kafka_publish_failures(self) -> None:
        """Increment the Kafka tracking publish failure counter."""

    def increment_stream_kafka_messages_consumed(self) -> None:
        """Increment the stream-event Kafka consumer success counter."""

    def increment_stream_kafka_consumer_failures(self) -> None:
        """Increment the stream-event Kafka consumer failure counter."""

    def observe_detector_pool_wait(self, camera_id: str, seconds: float) -> None:
        """Observe time a worker spent waiting for a detector checkout."""

        del camera_id, seconds

    def observe_embedding_queue_depth(self, depth: int) -> None:
        """Observe the current depth of the shared embedding request queue."""

        del depth

    def observe_enrichment_queue_depth(self, camera_id: str, depth: int) -> None:
        """Observe the current depth of the per-camera enrichment queue."""

        del camera_id, depth

    def observe_annotated_frame_queue_depth(self, camera_id: str, depth: int) -> None:
        """Observe the current depth of the per-camera annotated-frame output queue."""

        del camera_id, depth

    def observe_inference_ingress_queue_depth(self, camera_id: str, depth: int) -> None:
        """Observe the current depth of the per-camera inference ingress queue."""

        del camera_id, depth

    def increment_inference_frame_drop(self, camera_id: str) -> None:
        """Increment the counter of inference ingress frames dropped due to backpressure."""

        del camera_id


class NullMetricsRecorder(MetricsRecorder):
    """Provide a no-op metrics recorder when observability is disabled."""

    @property
    def registry(self) -> CollectorRegistry:
        """Return an empty registry for API compatibility."""

        return CollectorRegistry()


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
        self._stream_decoded_frames_total = Counter(
            "stream_decoded_frames_total",
            "Decoded frames observed by the realtime stream workers.",
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
        self._stream_worker_count = Gauge(
            "stream_worker_count",
            "Current number of active realtime stream workers.",
            registry=self._registry,
        )
        self._stream_worker_up = Gauge(
            "stream_worker_up",
            "Whether the realtime stream worker is active for a camera.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._stream_reconnect_attempts = Gauge(
            "stream_reconnect_attempts",
            "Current reconnect attempt count for a realtime stream worker.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._stream_current_fps = Gauge(
            "stream_current_fps",
            "Current sampled FPS for a realtime stream worker.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._stream_queue_latency_ms = Gauge(
            "stream_queue_latency_ms",
            "Current queue latency for a realtime stream worker in milliseconds.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._stream_decode_time_ms = Gauge(
            "stream_decode_time_ms",
            "Latest decode time for a realtime stream worker in milliseconds.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._stream_last_frame_age_seconds = Gauge(
            "stream_last_frame_age_seconds",
            "Age of the most recent frame queued by a realtime stream worker.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._tracking_worker_count = Gauge(
            "tracking_worker_count",
            "Current number of active tracking workers.",
            registry=self._registry,
        )
        self._tracking_worker_up = Gauge(
            "tracking_worker_up",
            "Whether the tracking worker is active for a camera.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._tracking_reconnect_attempts = Gauge(
            "tracking_reconnect_attempts",
            "Current reconnect attempt count for a tracking worker.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._tracking_processed_frames_total = Counter(
            "tracking_processed_frames_total",
            "Frames processed by the tracking pipeline.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._tracking_published_frames_total = Counter(
            "tracking_published_frames_total",
            "Annotated frames published back into MediaMTX by tracking workers.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._tracking_active_tracks = Gauge(
            "tracking_active_tracks",
            "Current number of active visible tracks per camera.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._tracking_last_frame_age_seconds = Gauge(
            "tracking_last_frame_age_seconds",
            "Age of the most recent processed tracking frame.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._tracking_identity_lookup_duration_seconds = Histogram(
            "tracking_identity_lookup_duration_seconds",
            "Milvus identity lookup duration for person re-identification.",
            labelnames=("camera_id",),
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
            registry=self._registry,
        )
        self._tracking_identity_resolutions_total = Counter(
            "tracking_identity_resolutions_total",
            "Identity resolution outcomes returned by the Milvus re-identification store.",
            labelnames=("camera_id", "result"),
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
        self._http_requests_total = Counter(
            "backend_http_requests_total",
            "HTTP requests handled by the backend control plane.",
            labelnames=("route", "method", "status_code"),
            registry=self._registry,
        )
        self._http_request_duration_seconds = Histogram(
            "backend_http_request_duration_seconds",
            "HTTP request duration for the backend control plane.",
            labelnames=("route", "method", "status_code"),
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=self._registry,
        )
        self._websocket_connections_current = Gauge(
            "backend_websocket_connections_current",
            "Current number of open websocket subscriptions.",
            registry=self._registry,
        )
        self._websocket_messages_sent_total = Counter(
            "backend_websocket_messages_sent_total",
            "Successful websocket messages sent to clients.",
            labelnames=("message_type",),
            registry=self._registry,
        )
        self._websocket_broadcast_failures_total = Counter(
            "backend_websocket_broadcast_failures_total",
            "Failed websocket send attempts during broadcast.",
            labelnames=("message_type",),
            registry=self._registry,
        )
        self._dependency_health = Gauge(
            "backend_dependency_health",
            "Binary dependency health reported by the backend.",
            labelnames=("component",),
            registry=self._registry,
        )
        self._tracking_kafka_messages_published_total = Counter(
            "tracking_kafka_messages_published_total",
            "Tracking metadata messages successfully published to Kafka.",
            registry=self._registry,
        )
        self._tracking_kafka_publish_failures_total = Counter(
            "tracking_kafka_publish_failures_total",
            "Tracking metadata publish attempts that failed for Kafka.",
            registry=self._registry,
        )
        self._stream_kafka_messages_consumed_total = Counter(
            "stream_kafka_messages_consumed_total",
            "Kafka stream events successfully consumed by the backend.",
            registry=self._registry,
        )
        self._stream_kafka_consumer_failures_total = Counter(
            "stream_kafka_consumer_failures_total",
            "Kafka stream event consumer failures inside the backend.",
            registry=self._registry,
        )
        self._detector_pool_wait_seconds = Histogram(
            "detector_pool_wait_seconds",
            "Time a tracking worker waited to acquire a detector from the pool.",
            labelnames=("camera_id",),
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
            registry=self._registry,
        )
        self._embedding_queue_depth = Gauge(
            "embedding_queue_depth",
            "Current number of pending embedding requests in the shared embedding queue.",
            registry=self._registry,
        )
        self._enrichment_queue_depth = Gauge(
            "enrichment_queue_depth",
            "Current number of pending items in the per-camera enrichment queue.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._annotated_frame_queue_depth = Gauge(
            "annotated_frame_queue_depth",
            "Current number of annotated frames buffered in the per-camera output queue.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._inference_ingress_queue_depth = Gauge(
            "inference_ingress_queue_depth",
            "Current number of samples queued in the per-camera inference ingress queue.",
            labelnames=("camera_id",),
            registry=self._registry,
        )
        self._inference_frame_drops_total = Counter(
            "inference_frame_drops_total",
            "Inference ingress samples dropped due to full queue backpressure.",
            labelnames=("camera_id",),
            registry=self._registry,
        )

    @property
    def registry(self) -> CollectorRegistry:
        """Return the Prometheus registry used by this metrics recorder."""

        return self._registry

    def record_frame_received(self, camera_id: str) -> None:
        self._frames_received_total.labels(camera_id=camera_id).inc()

    def record_frame_dropped(self, camera_id: str) -> None:
        self._frames_dropped_total.labels(camera_id=camera_id).inc()

    def increment_stream_decoded_frames(self, camera_id: str, frame_count: int) -> None:
        if frame_count > 0:
            self._stream_decoded_frames_total.labels(camera_id=camera_id).inc(frame_count)

    def observe_frame_processing_latency(self, camera_id: str, latency_ms: float) -> None:
        self._frame_processing_latency_ms.labels(camera_id=camera_id).observe(latency_ms)

    def set_stream_worker_count(self, worker_count: int) -> None:
        self._stream_worker_count.set(worker_count)

    def set_stream_worker_up(self, camera_id: str, is_up: bool) -> None:
        self._stream_worker_up.labels(camera_id=camera_id).set(1.0 if is_up else 0.0)

    def set_stream_reconnect_attempts(self, camera_id: str, attempt_count: int) -> None:
        self._stream_reconnect_attempts.labels(camera_id=camera_id).set(float(attempt_count))

    def set_stream_current_fps(self, camera_id: str, fps: float) -> None:
        self._stream_current_fps.labels(camera_id=camera_id).set(max(fps, 0.0))

    def set_stream_queue_latency_ms(self, camera_id: str, latency_ms: float) -> None:
        self._stream_queue_latency_ms.labels(camera_id=camera_id).set(max(latency_ms, 0.0))

    def set_stream_decode_time_ms(self, camera_id: str, decode_time_ms: float) -> None:
        self._stream_decode_time_ms.labels(camera_id=camera_id).set(max(decode_time_ms, 0.0))

    def set_stream_last_frame_age_seconds(self, camera_id: str, age_seconds: float) -> None:
        self._stream_last_frame_age_seconds.labels(camera_id=camera_id).set(
            max(age_seconds, 0.0),
        )

    def set_tracking_worker_count(self, worker_count: int) -> None:
        self._tracking_worker_count.set(worker_count)

    def set_tracking_worker_up(self, camera_id: str, is_up: bool) -> None:
        self._tracking_worker_up.labels(camera_id=camera_id).set(1.0 if is_up else 0.0)

    def set_tracking_reconnect_attempts(self, camera_id: str, attempt_count: int) -> None:
        self._tracking_reconnect_attempts.labels(camera_id=camera_id).set(float(attempt_count))

    def increment_tracking_processed_frames(self, camera_id: str, frame_count: int) -> None:
        if frame_count > 0:
            self._tracking_processed_frames_total.labels(camera_id=camera_id).inc(frame_count)

    def increment_tracking_published_frames(self, camera_id: str, frame_count: int) -> None:
        if frame_count > 0:
            self._tracking_published_frames_total.labels(camera_id=camera_id).inc(frame_count)

    def set_tracking_active_tracks(self, camera_id: str, active_tracks: int) -> None:
        self._tracking_active_tracks.labels(camera_id=camera_id).set(float(active_tracks))

    def set_tracking_last_frame_age_seconds(self, camera_id: str, age_seconds: float) -> None:
        self._tracking_last_frame_age_seconds.labels(camera_id=camera_id).set(
            max(age_seconds, 0.0),
        )

    def observe_tracking_identity_lookup_duration(
        self,
        camera_id: str,
        duration_seconds: float,
    ) -> None:
        self._tracking_identity_lookup_duration_seconds.labels(camera_id=camera_id).observe(
            max(duration_seconds, 0.0),
        )

    def increment_tracking_identity_resolution(
        self,
        camera_id: str,
        matched_existing: bool,
    ) -> None:
        result = "matched_existing" if matched_existing else "new_identity"
        self._tracking_identity_resolutions_total.labels(
            camera_id=camera_id,
            result=result,
        ).inc()

    def set_queue_size(self, size: int) -> None:
        self._queue_size.set(size)

    def set_system_cpu_usage_percent(self, usage_percent: float) -> None:
        self._system_cpu_usage_percent.set(usage_percent)

    def set_process_cpu_usage_percent(self, usage_percent: float) -> None:
        self._process_cpu_usage_percent.set(usage_percent)

    def set_system_memory_usage_bytes(self, memory_bytes: int) -> None:
        self._system_memory_usage_bytes.set(memory_bytes)

    def set_process_memory_usage_bytes(self, memory_bytes: int) -> None:
        self._process_memory_usage_bytes.set(memory_bytes)

    def increment_system_network_receive_bytes(self, byte_count: int) -> None:
        if byte_count > 0:
            self._system_network_receive_bytes_total.inc(byte_count)

    def increment_system_network_transmit_bytes(self, byte_count: int) -> None:
        if byte_count > 0:
            self._system_network_transmit_bytes_total.inc(byte_count)

    def observe_http_request(
        self,
        route: str,
        method: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        labels = {
            "route": route,
            "method": method.upper(),
            "status_code": str(status_code),
        }
        self._http_requests_total.labels(**labels).inc()
        self._http_request_duration_seconds.labels(**labels).observe(
            max(duration_seconds, 0.0),
        )

    def increment_websocket_connections(self) -> None:
        self._websocket_connections_current.inc()

    def decrement_websocket_connections(self) -> None:
        self._websocket_connections_current.dec()

    def record_websocket_message_sent(self, message_type: str) -> None:
        self._websocket_messages_sent_total.labels(message_type=message_type).inc()

    def record_websocket_broadcast_failure(self, message_type: str) -> None:
        self._websocket_broadcast_failures_total.labels(message_type=message_type).inc()

    def set_dependency_health(self, component: str, is_healthy: bool) -> None:
        self._dependency_health.labels(component=component).set(1.0 if is_healthy else 0.0)

    def increment_tracking_kafka_messages_published(self) -> None:
        self._tracking_kafka_messages_published_total.inc()

    def increment_tracking_kafka_publish_failures(self) -> None:
        self._tracking_kafka_publish_failures_total.inc()

    def increment_stream_kafka_messages_consumed(self) -> None:
        self._stream_kafka_messages_consumed_total.inc()

    def increment_stream_kafka_consumer_failures(self) -> None:
        self._stream_kafka_consumer_failures_total.inc()

    def observe_detector_pool_wait(self, camera_id: str, seconds: float) -> None:
        self._detector_pool_wait_seconds.labels(camera_id=camera_id).observe(max(seconds, 0.0))

    def observe_embedding_queue_depth(self, depth: int) -> None:
        self._embedding_queue_depth.set(depth)

    def observe_enrichment_queue_depth(self, camera_id: str, depth: int) -> None:
        self._enrichment_queue_depth.labels(camera_id=camera_id).set(depth)

    def observe_annotated_frame_queue_depth(self, camera_id: str, depth: int) -> None:
        self._annotated_frame_queue_depth.labels(camera_id=camera_id).set(depth)

    def observe_inference_ingress_queue_depth(self, camera_id: str, depth: int) -> None:
        self._inference_ingress_queue_depth.labels(camera_id=camera_id).set(depth)

    def increment_inference_frame_drop(self, camera_id: str) -> None:
        self._inference_frame_drops_total.labels(camera_id=camera_id).inc()

