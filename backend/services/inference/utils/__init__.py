"""services.inference.utils — Prometheus metrics for the Inference service."""
from services.inference.utils.metrics import (
    inference_latency,
    frames_processed,
    frames_dropped,
    gpu_memory_bytes,
    update_gpu_memory,
    METRICS_PORT,
)

__all__ = [
    "inference_latency",
    "frames_processed",
    "frames_dropped",
    "gpu_memory_bytes",
    "update_gpu_memory",
    "METRICS_PORT",
]
