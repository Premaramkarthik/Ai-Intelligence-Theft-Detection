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

camera_state_transitions = Counter(
    "mediabridge_camera_state_transitions_total",
    "Camera online/offline/reconnecting transitions",
    ["camera_id", "state"],
)

redis_reconnects = Counter(
    "mediabridge_redis_reconnects_total",
    "Redis reconnect attempts for MediaBridge",
)

frame_queue_depth = Gauge(
    "mediabridge_frame_queue_depth",
    "Observed global frame queue depth",
)
