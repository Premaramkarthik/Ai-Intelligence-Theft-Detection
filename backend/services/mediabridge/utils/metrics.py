"""Prometheus metrics for MediaBridge service."""
from prometheus_client import Counter, Gauge

METRICS_PORT = 9102

frames_captured = Counter(
    "mediabridge_frames_captured_total",
    "Total frames captured from all cameras",
    ["camera_id"],
)

frames_dropped = Counter(
    "mediabridge_frames_dropped_total",
    "Frames dropped due to SHM overflow or encoding errors",
    ["camera_id"],
)

cameras_active = Gauge(
    "mediabridge_cameras_active",
    "Number of currently active camera streams",
)

frame_latency = Gauge(
    "mediabridge_capture_latency_ms",
    "Time between capture and SHM write in ms",
    ["camera_id"],
)
