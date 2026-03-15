"""Prometheus metrics for the Inference service."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

METRICS_PORT = 9101

inference_latency = Histogram(
    "inference_latency_seconds",
    "End-to-end per-frame D1→D5 latency",
    buckets=[0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.5, 1.0],
)

frames_processed = Counter(
    "inference_frames_processed_total",
    "Total frames successfully processed",
)

frames_dropped = Counter(
    "inference_frames_dropped_total",
    "Stale / unreadable frames skipped",
)

classification_attempts = Counter(
    "inference_classification_attempts_total",
    "Classification attempts started",
)

classification_failures = Counter(
    "inference_classification_failures_total",
    "Classification failures",
)

incidents_emitted = Counter(
    "inference_incidents_emitted_total",
    "Incidents emitted by inference",
)

detector_failures = Counter(
    "inference_detector_failures_total",
    "Detector execution failures",
)

redis_reconnects = Counter(
    "inference_redis_reconnects_total",
    "Inference Redis reconnect attempts",
)

queue_depth = Gauge(
    "inference_frame_queue_depth",
    "Observed shared frame queue depth",
)

camera_queue_depth = Gauge(
    "inference_camera_queue_depth",
    "Per-camera inference queue depth",
    ["camera_id"],
)

camera_frame_age_seconds = Gauge(
    "inference_camera_frame_age_seconds",
    "Observed age of dequeued frames by camera",
    ["camera_id"],
)

stale_frame_drops = Counter(
    "inference_stale_frame_drops_total",
    "Dropped stale frames by camera",
    ["camera_id"],
)

reid_available = Gauge(
    "inference_reid_available",
    "ReID availability, 1 when enabled",
)

gpu_memory_bytes = Gauge(
    "inference_gpu_memory_bytes",
    "Current GPU memory usage in bytes",
)


def update_gpu_memory() -> None:
    """Call once per batch to refresh GPU memory gauge."""
    try:
        import torch  # noqa: PLC0415
        if torch.cuda.is_available():
            gpu_memory_bytes.set(torch.cuda.memory_allocated())
    except Exception:
        pass
