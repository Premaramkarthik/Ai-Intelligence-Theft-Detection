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
