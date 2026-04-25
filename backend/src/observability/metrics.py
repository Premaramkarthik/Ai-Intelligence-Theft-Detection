"""Prometheus metric registry and recorder helpers."""

from __future__ import annotations

from typing import Protocol

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class MetricsRecorder(Protocol):
    """Structural protocol implemented by metrics recorders."""

    registry: CollectorRegistry


class NullMetricsRecorder:
    """No-op metrics recorder used when metrics are disabled."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry()

    def __getattr__(self, _name: str):
        def _noop(*_args, **_kwargs) -> None:
            return None

        return _noop


class PrometheusMetrics:
    """Own Prometheus metric families and provide typed record helpers."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry(auto_describe=True)

        # Streaming / pipeline metrics.
        self._frames_received = Counter(
            "frames_received",
            "Total frames received from capture workers.",
            ("camera_id",),
            registry=self.registry,
        )
        self._frames_dropped = Counter(
            "frames_dropped",
            "Total frames dropped before processing.",
            ("camera_id", "reason"),
            registry=self.registry,
        )
        self._stream_decoded_frames = Counter(
            "stream_decoded_frames",
            "Total frames successfully decoded by capture workers.",
            ("camera_id",),
            registry=self.registry,
        )
        self._frame_processing_latency_ms = Histogram(
            "frame_processing_latency_ms",
            "End-to-end frame processing latency in milliseconds.",
            ("camera_id",),
            buckets=(5, 10, 16, 25, 33, 50, 75, 100, 150, 250, 500, 1000, 2000, 5000),
            registry=self.registry,
        )
        self._detection_latency_ms = Histogram(
            "detection_latency_ms",
            "Detection stage latency in milliseconds.",
            buckets=(1, 5, 10, 16, 25, 33, 50, 75, 100, 150, 250, 500, 1000),
            registry=self.registry,
        )
        self._tracking_latency_ms = Histogram(
            "tracking_latency_ms",
            "Tracking stage latency in milliseconds.",
            buckets=(0.5, 1, 5, 10, 16, 25, 33, 50, 75, 100, 150, 250, 500),
            registry=self.registry,
        )
        self._reid_latency_ms = Histogram(
            "reid_latency_ms",
            "Re-identification stage latency in milliseconds.",
            buckets=(0.5, 1, 5, 10, 16, 25, 33, 50, 75, 100, 150, 250, 500, 1000),
            registry=self.registry,
        )
        self._identity_assignment_latency_ms = Histogram(
            "identity_assignment_latency_ms",
            "Identity assignment stage latency in milliseconds.",
            buckets=(0.5, 1, 5, 10, 16, 25, 33, 50, 75, 100, 150, 250, 500, 1000),
            registry=self.registry,
        )
        self._stream_worker_count = Gauge(
            "stream_worker_count",
            "Current number of active capture workers.",
            registry=self.registry,
        )
        self._stream_worker_up = Gauge(
            "stream_worker_up",
            "Whether a capture worker is healthy and running.",
            ("camera_id",),
            registry=self.registry,
        )
        self._stream_reconnect_attempts = Gauge(
            "stream_reconnect_attempts",
            "Current reconnect attempts recorded for a capture worker.",
            ("camera_id",),
            registry=self.registry,
        )
        self._stream_current_fps = Gauge(
            "stream_current_fps",
            "Recent decoded frame rate per camera.",
            ("camera_id",),
            registry=self.registry,
        )
        self._stream_queue_latency_ms = Gauge(
            "stream_queue_latency_ms",
            "Latest time a frame spent queued before processing in milliseconds.",
            ("camera_id",),
            registry=self.registry,
        )
        self._stream_decode_time_ms = Gauge(
            "stream_decode_time_ms",
            "Latest frame decode time in milliseconds.",
            ("camera_id",),
            registry=self.registry,
        )
        self._stream_last_frame_age_seconds = Gauge(
            "stream_last_frame_age_seconds",
            "Age of the last frame observed for each camera.",
            ("camera_id",),
            registry=self.registry,
        )
        self._tracking_worker_count = Gauge(
            "tracking_worker_count",
            "Current number of active tracking workers.",
            registry=self.registry,
        )
        self._tracking_worker_up = Gauge(
            "tracking_worker_up",
            "Whether tracking is healthy for a camera.",
            ("camera_id",),
            registry=self.registry,
        )
        self._tracking_processed_frames = Counter(
            "tracking_processed_frames",
            "Total frames processed by the tracking stage.",
            ("camera_id",),
            registry=self.registry,
        )
        self._tracking_published_frames = Counter(
            "tracking_published_frames",
            "Total frames published downstream by the tracking stage.",
            ("camera_id",),
            registry=self.registry,
        )
        self._tracking_active_tracks = Gauge(
            "tracking_active_tracks",
            "Current active track count per camera.",
            ("camera_id",),
            registry=self.registry,
        )
        self._tracking_identity_lookup_duration_seconds = Histogram(
            "tracking_identity_lookup_duration_seconds",
            "Milvus identity lookup duration in seconds.",
            ("camera_id",),
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
            registry=self.registry,
        )
        self._tracking_identity_resolutions = Counter(
            "tracking_identity_resolutions",
            "Identity resolutions performed by the tracking pipeline.",
            ("camera_id", "matched_existing"),
            registry=self.registry,
        )
        self._queue_size = Gauge(
            "queue_size",
            "Current shared frame buffer depth.",
            registry=self.registry,
        )
        self._active_cameras = Gauge(
            "active_cameras",
            "Current number of active cameras in the OpenCV runtime.",
            registry=self.registry,
        )

        # System metrics.
        self._system_cpu_usage_percent = Gauge(
            "system_cpu_usage_percent",
            "Host CPU usage percent.",
            registry=self.registry,
        )
        self._process_cpu_usage_percent = Gauge(
            "process_cpu_usage_percent",
            "Backend process CPU usage percent.",
            registry=self.registry,
        )
        self._system_memory_usage_bytes = Gauge(
            "system_memory_usage_bytes",
            "Host memory usage in bytes.",
            registry=self.registry,
        )
        self._process_memory_usage_bytes = Gauge(
            "process_memory_usage_bytes",
            "Backend process RSS memory in bytes.",
            registry=self.registry,
        )
        self._system_network_receive_bytes = Counter(
            "system_network_receive_bytes",
            "Host network bytes received.",
            registry=self.registry,
        )
        self._system_network_transmit_bytes = Counter(
            "system_network_transmit_bytes",
            "Host network bytes transmitted.",
            registry=self.registry,
        )
        self._system_disk_read_bytes = Counter(
            "system_disk_read_bytes",
            "Host disk bytes read.",
            registry=self.registry,
        )
        self._system_disk_write_bytes = Counter(
            "system_disk_write_bytes",
            "Host disk bytes written.",
            registry=self.registry,
        )

        # HTTP metrics.
        self._backend_http_requests = Counter(
            "backend_http_requests",
            "Total HTTP requests processed by the backend.",
            ("route", "method", "status"),
            registry=self.registry,
        )
        self._backend_http_request_duration_seconds = Histogram(
            "backend_http_request_duration_seconds",
            "HTTP request duration in seconds.",
            ("route", "method"),
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
            registry=self.registry,
        )
        self._backend_http_inprogress_requests = Gauge(
            "backend_http_inprogress_requests",
            "Current in-flight HTTP requests.",
            ("route", "method"),
            registry=self.registry,
        )
        self._backend_http_exceptions = Counter(
            "backend_http_exceptions",
            "Unhandled HTTP request exceptions.",
            ("route", "method", "exception"),
            registry=self.registry,
        )

        # WebSocket metrics.
        self._backend_websocket_connections_current = Gauge(
            "backend_websocket_connections_current",
            "Current number of open websocket subscriptions.",
            registry=self.registry,
        )
        self._backend_websocket_messages_sent = Counter(
            "backend_websocket_messages_sent",
            "Successful websocket messages sent to clients.",
            ("message_type",),
            registry=self.registry,
        )
        self._backend_websocket_broadcast_failures = Counter(
            "backend_websocket_broadcast_failures",
            "Failed websocket send attempts during broadcast.",
            ("message_type",),
            registry=self.registry,
        )
        self._backend_websocket_broadcast_duration_seconds = Histogram(
            "backend_websocket_broadcast_duration_seconds",
            "WebSocket broadcast duration in seconds.",
            ("message_type",),
            buckets=(0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2),
            registry=self.registry,
        )

        # Dependency metrics.
        self._backend_dependency_health = Gauge(
            "backend_dependency_health",
            "Health state of backend dependencies and background services.",
            ("component",),
            registry=self.registry,
        )
        self._tracking_kafka_messages_published = Counter(
            "tracking_kafka_messages_published",
            "Tracking messages successfully published to Kafka.",
            registry=self.registry,
        )
        self._tracking_kafka_publish_failures = Counter(
            "tracking_kafka_publish_failures",
            "Tracking Kafka publish failures.",
            registry=self.registry,
        )
        self._stream_kafka_messages_consumed = Counter(
            "stream_kafka_messages_consumed",
            "Realtime stream Kafka messages consumed by topic.",
            ("topic",),
            registry=self.registry,
        )
        self._stream_kafka_consumer_failures = Counter(
            "stream_kafka_consumer_failures",
            "Realtime stream Kafka consumer failures.",
            registry=self.registry,
        )

        # Inference metrics.
        self._inference_frame_drops = Counter(
            "inference_frame_drops",
            "Frames or inference batches dropped before inference execution.",
            ("camera_id", "reason"),
            registry=self.registry,
        )
        self._inference_queue_depth = Gauge(
            "inference_queue_depth",
            "Current inference queue depth per camera.",
            ("camera_id",),
            registry=self.registry,
        )
        self._inference_queue_full = Counter(
            "inference_queue_full",
            "Inference queue full events.",
            ("camera_id",),
            registry=self.registry,
        )
        self._inference_gate_rejections = Counter(
            "inference_gate_rejections",
            "Inference dispatch gate rejection counts.",
            ("camera_id", "reason"),
            registry=self.registry,
        )
        self._inference_requests = Counter(
            "inference_requests",
            "Inference requests grouped by strategy, model, and outcome.",
            ("strategy", "model_name", "outcome"),
            registry=self.registry,
        )
        self._inference_results = Counter(
            "inference_results",
            "Inference results grouped by alert level.",
            ("strategy", "model_name", "alert_level"),
            registry=self.registry,
        )
        self._inference_preprocessing_duration_seconds = Histogram(
            "inference_preprocessing_duration_seconds",
            "Inference preprocessing duration in seconds.",
            ("strategy", "model_name"),
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
            registry=self.registry,
        )
        self._inference_execution_duration_seconds = Histogram(
            "inference_execution_duration_seconds",
            "Inference execution duration in seconds.",
            ("strategy", "model_name"),
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
            registry=self.registry,
        )
        self._inference_delivery_duration_seconds = Histogram(
            "inference_delivery_duration_seconds",
            "Inference delivery duration per sink in seconds.",
            ("sink",),
            buckets=(0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2),
            registry=self.registry,
        )
        self._inference_total_duration_seconds = Histogram(
            "inference_total_duration_seconds",
            "End-to-end inference duration in seconds.",
            ("strategy", "model_name"),
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
            registry=self.registry,
        )
        self._inference_sample_age_seconds = Histogram(
            "inference_sample_age_seconds",
            "Age of samples when inference results are emitted in seconds.",
            ("strategy", "model_name"),
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30),
            registry=self.registry,
        )
        self._triton_connected = Gauge(
            "triton_connected",
            "Whether the Triton gRPC client is currently connected.",
            registry=self.registry,
        )
        self._triton_connect_failures = Counter(
            "triton_connect_failures",
            "Failed Triton connection attempts.",
            registry=self.registry,
        )
        self._triton_inflight_requests = Gauge(
            "triton_inflight_requests",
            "Current number of in-flight Triton requests.",
            registry=self.registry,
        )

        # WebRTC metrics.
        self._webrtc_peer_connections_current = Gauge(
            "webrtc_peer_connections_current",
            "Current number of active WebRTC peer connections.",
            registry=self.registry,
        )
        self._webrtc_viewers_current = Gauge(
            "webrtc_viewers_current",
            "Current WebRTC viewer count per camera.",
            ("camera_id",),
            registry=self.registry,
        )
        self._webrtc_offers = Counter(
            "webrtc_offers",
            "WebRTC offer attempts grouped by result.",
            ("result",),
            registry=self.registry,
        )
        self._webrtc_ice_gather_duration_seconds = Histogram(
            "webrtc_ice_gather_duration_seconds",
            "WebRTC ICE gathering duration in seconds.",
            buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 15),
            registry=self.registry,
        )

    # ------------------------------------------------------------------
    # Pipeline / tracking
    # ------------------------------------------------------------------

    def record_frame_received(self, camera_id: str) -> None:
        self._frames_received.labels(camera_id=camera_id).inc()

    def record_frame_dropped(self, camera_id: str, reason: str = "unknown") -> None:
        self._frames_dropped.labels(camera_id=camera_id, reason=reason).inc()

    def increment_stream_decoded_frames(self, camera_id: str, amount: int = 1) -> None:
        self._stream_decoded_frames.labels(camera_id=camera_id).inc(amount)

    def observe_frame_processing_latency(self, camera_id: str, latency_ms: float) -> None:
        self._frame_processing_latency_ms.labels(camera_id=camera_id).observe(max(latency_ms, 0.0))

    def observe_detection_latency(self, latency_ms: float) -> None:
        self._detection_latency_ms.observe(max(latency_ms, 0.0))

    def observe_tracking_latency(self, latency_ms: float) -> None:
        self._tracking_latency_ms.observe(max(latency_ms, 0.0))

    def observe_reid_latency(self, latency_ms: float) -> None:
        self._reid_latency_ms.observe(max(latency_ms, 0.0))

    def observe_identity_assignment_latency(self, latency_ms: float) -> None:
        self._identity_assignment_latency_ms.observe(max(latency_ms, 0.0))

    def set_stream_worker_count(self, count: int) -> None:
        self._stream_worker_count.set(max(float(count), 0.0))

    def set_stream_worker_up(self, camera_id: str, is_up: bool) -> None:
        self._stream_worker_up.labels(camera_id=camera_id).set(1.0 if is_up else 0.0)

    def set_stream_reconnect_attempts(self, camera_id: str, attempts: int) -> None:
        self._stream_reconnect_attempts.labels(camera_id=camera_id).set(max(float(attempts), 0.0))

    def set_stream_current_fps(self, camera_id: str, fps: float) -> None:
        self._stream_current_fps.labels(camera_id=camera_id).set(max(fps, 0.0))

    def set_stream_queue_latency_ms(self, camera_id: str, latency_ms: float) -> None:
        self._stream_queue_latency_ms.labels(camera_id=camera_id).set(max(latency_ms, 0.0))

    def set_stream_decode_time_ms(self, camera_id: str, decode_time_ms: float) -> None:
        self._stream_decode_time_ms.labels(camera_id=camera_id).set(max(decode_time_ms, 0.0))

    def set_stream_last_frame_age_seconds(self, camera_id: str, age_seconds: float) -> None:
        self._stream_last_frame_age_seconds.labels(camera_id=camera_id).set(max(age_seconds, 0.0))

    def set_tracking_worker_count(self, count: int) -> None:
        self._tracking_worker_count.set(max(float(count), 0.0))

    def set_tracking_worker_up(self, camera_id: str, is_up: bool) -> None:
        self._tracking_worker_up.labels(camera_id=camera_id).set(1.0 if is_up else 0.0)

    def increment_tracking_processed_frames(self, camera_id: str, amount: int = 1) -> None:
        self._tracking_processed_frames.labels(camera_id=camera_id).inc(amount)

    def increment_tracking_published_frames(self, camera_id: str, amount: int = 1) -> None:
        self._tracking_published_frames.labels(camera_id=camera_id).inc(amount)

    def set_tracking_active_tracks(self, camera_id: str, active_tracks: int) -> None:
        self._tracking_active_tracks.labels(camera_id=camera_id).set(max(float(active_tracks), 0.0))

    def observe_tracking_identity_lookup_duration(self, camera_id: str, seconds: float) -> None:
        self._tracking_identity_lookup_duration_seconds.labels(camera_id=camera_id).observe(max(seconds, 0.0))

    def increment_tracking_identity_resolution(self, camera_id: str, *, matched_existing: bool) -> None:
        self._tracking_identity_resolutions.labels(
            camera_id=camera_id,
            matched_existing=str(bool(matched_existing)).lower(),
        ).inc()

    def set_queue_size(self, size: int) -> None:
        self._queue_size.set(max(float(size), 0.0))

    def set_active_cameras(self, count: int) -> None:
        self._active_cameras.set(max(float(count), 0.0))

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------

    def set_system_cpu_usage_percent(self, percent: float) -> None:
        self._system_cpu_usage_percent.set(max(percent, 0.0))

    def set_process_cpu_usage_percent(self, percent: float) -> None:
        self._process_cpu_usage_percent.set(max(percent, 0.0))

    def set_system_memory_usage_bytes(self, value: int | float) -> None:
        self._system_memory_usage_bytes.set(max(float(value), 0.0))

    def set_process_memory_usage_bytes(self, value: int | float) -> None:
        self._process_memory_usage_bytes.set(max(float(value), 0.0))

    def increment_system_network_receive_bytes(self, value: int | float) -> None:
        if value > 0:
            self._system_network_receive_bytes.inc(float(value))

    def increment_system_network_transmit_bytes(self, value: int | float) -> None:
        if value > 0:
            self._system_network_transmit_bytes.inc(float(value))

    def increment_system_disk_read_bytes(self, value: int | float) -> None:
        if value > 0:
            self._system_disk_read_bytes.inc(float(value))

    def increment_system_disk_write_bytes(self, value: int | float) -> None:
        if value > 0:
            self._system_disk_write_bytes.inc(float(value))

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def increment_http_inprogress(self, route: str, method: str) -> None:
        self._backend_http_inprogress_requests.labels(route=route, method=method).inc()

    def decrement_http_inprogress(self, route: str, method: str) -> None:
        self._backend_http_inprogress_requests.labels(route=route, method=method).dec()

    def observe_http_request(self, route: str, method: str, status_code: int, duration_seconds: float) -> None:
        self._backend_http_requests.labels(
            route=route,
            method=method,
            status=str(status_code),
        ).inc()
        self._backend_http_request_duration_seconds.labels(
            route=route,
            method=method,
        ).observe(max(duration_seconds, 0.0))

    def record_http_exception(self, route: str, method: str, exception_name: str) -> None:
        self._backend_http_exceptions.labels(
            route=route,
            method=method,
            exception=exception_name,
        ).inc()

    # ------------------------------------------------------------------
    # WebSocket / dependency / Kafka
    # ------------------------------------------------------------------

    def increment_websocket_connections(self) -> None:
        self._backend_websocket_connections_current.inc()

    def decrement_websocket_connections(self) -> None:
        self._backend_websocket_connections_current.dec()

    def record_websocket_message_sent(self, message_type: str) -> None:
        self._backend_websocket_messages_sent.labels(message_type=message_type).inc()

    def record_websocket_broadcast_failure(self, message_type: str) -> None:
        self._backend_websocket_broadcast_failures.labels(message_type=message_type).inc()

    def observe_websocket_broadcast_duration(self, message_type: str, duration_seconds: float) -> None:
        self._backend_websocket_broadcast_duration_seconds.labels(
            message_type=message_type
        ).observe(max(duration_seconds, 0.0))

    def set_dependency_health(self, component: str, healthy: bool) -> None:
        self._backend_dependency_health.labels(component=component).set(1.0 if healthy else 0.0)

    def increment_tracking_kafka_messages_published(self) -> None:
        self._tracking_kafka_messages_published.inc()

    def increment_tracking_kafka_publish_failures(self) -> None:
        self._tracking_kafka_publish_failures.inc()

    def increment_stream_kafka_messages_consumed(self, topic: str = "unknown") -> None:
        self._stream_kafka_messages_consumed.labels(topic=topic).inc()

    def increment_stream_kafka_consumer_failures(self) -> None:
        self._stream_kafka_consumer_failures.inc()

    # ------------------------------------------------------------------
    # Inference / Triton
    # ------------------------------------------------------------------

    def increment_inference_frame_drop(self, camera_id: str, reason: str = "unknown") -> None:
        self._inference_frame_drops.labels(camera_id=camera_id, reason=reason).inc()

    def set_inference_queue_depth(self, camera_id: str, depth: int) -> None:
        self._inference_queue_depth.labels(camera_id=camera_id).set(max(float(depth), 0.0))

    def increment_inference_queue_full(self, camera_id: str) -> None:
        self._inference_queue_full.labels(camera_id=camera_id).inc()

    def increment_inference_gate_rejection(self, camera_id: str, reason: str) -> None:
        self._inference_gate_rejections.labels(camera_id=camera_id, reason=reason).inc()

    def increment_inference_request(self, strategy: str, model_name: str, outcome: str) -> None:
        self._inference_requests.labels(
            strategy=strategy,
            model_name=model_name,
            outcome=outcome,
        ).inc()

    def increment_inference_result(self, strategy: str, model_name: str, alert_level: str) -> None:
        self._inference_results.labels(
            strategy=strategy,
            model_name=model_name,
            alert_level=alert_level,
        ).inc()

    def observe_inference_preprocessing_latency(self, strategy: str, model_name: str, seconds: float) -> None:
        self._inference_preprocessing_duration_seconds.labels(
            strategy=strategy,
            model_name=model_name,
        ).observe(max(seconds, 0.0))

    def observe_inference_execution_latency(self, strategy: str, model_name: str, seconds: float) -> None:
        self._inference_execution_duration_seconds.labels(
            strategy=strategy,
            model_name=model_name,
        ).observe(max(seconds, 0.0))

    def observe_inference_delivery_latency(self, sink: str, seconds: float) -> None:
        self._inference_delivery_duration_seconds.labels(sink=sink).observe(max(seconds, 0.0))

    def observe_inference_total_latency(self, strategy: str, model_name: str, seconds: float) -> None:
        self._inference_total_duration_seconds.labels(
            strategy=strategy,
            model_name=model_name,
        ).observe(max(seconds, 0.0))

    def observe_inference_sample_age(self, strategy: str, model_name: str, seconds: float) -> None:
        self._inference_sample_age_seconds.labels(
            strategy=strategy,
            model_name=model_name,
        ).observe(max(seconds, 0.0))

    def set_triton_connected(self, connected: bool) -> None:
        self._triton_connected.set(1.0 if connected else 0.0)

    def increment_triton_connect_failure(self) -> None:
        self._triton_connect_failures.inc()

    def set_triton_inflight_requests(self, count: int) -> None:
        self._triton_inflight_requests.set(max(float(count), 0.0))

    def increment_triton_inflight_requests(self) -> None:
        self._triton_inflight_requests.inc()

    def decrement_triton_inflight_requests(self) -> None:
        self._triton_inflight_requests.dec()

    # ------------------------------------------------------------------
    # WebRTC
    # ------------------------------------------------------------------

    def set_webrtc_peer_connections(self, count: int) -> None:
        self._webrtc_peer_connections_current.set(max(float(count), 0.0))

    def set_webrtc_viewers(self, camera_id: str, count: int) -> None:
        self._webrtc_viewers_current.labels(camera_id=camera_id).set(max(float(count), 0.0))

    def increment_webrtc_offer(self, result: str) -> None:
        self._webrtc_offers.labels(result=result).inc()

    def observe_webrtc_ice_gather_duration(self, seconds: float) -> None:
        self._webrtc_ice_gather_duration_seconds.observe(max(seconds, 0.0))
