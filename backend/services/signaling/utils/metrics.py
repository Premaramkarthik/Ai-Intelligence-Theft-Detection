from __future__ import annotations

from prometheus_client import Counter, Gauge

websocket_clients = Gauge(
    "signaling_websocket_clients",
    "Connected signaling websocket clients",
    ["channel"],
)

snapshot_failures = Counter(
    "signaling_snapshot_failures_total",
    "Snapshot/JPEG fetch failures",
    ["camera_id"],
)

webrtc_active_peers = Gauge(
    "signaling_webrtc_active_peers",
    "Active WebRTC peer connections",
)

webrtc_viewers_per_camera = Gauge(
    "signaling_webrtc_viewers_per_camera",
    "Active WebRTC viewers per camera",
    ["camera_id"],
)

webrtc_negotiation_failures = Counter(
    "signaling_webrtc_negotiation_failures_total",
    "Failed WebRTC negotiations",
    ["camera_id"],
)

webrtc_ice_failures = Counter(
    "signaling_webrtc_ice_failures_total",
    "WebRTC ICE/connection failures",
    ["camera_id"],
)
