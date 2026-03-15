from __future__ import annotations

CAMERA_SOURCES_KEY = "camera_sources"
GLOBAL_FRAME_QUEUE_KEY = "frames"
FRAME_QUEUE_PATTERN = "frames:*"
INCIDENT_STREAM_KEY = "stream:incidents"
TELEMETRY_CHANNEL_PATTERN = "telemetry:*"
INCIDENT_CHANNEL_PATTERN = "incidents:*"
FRAME_POINTER_PATTERN = "frame_ptr:*"
CONFIG_KEY_PATTERN = "config:*"
REID_EMBEDDING_PREFIX = "reid:embeddings:"


def frame_queue_key(camera_id: str | None = None) -> str:
    if camera_id is None:
        return GLOBAL_FRAME_QUEUE_KEY
    return f"frames:{camera_id}"


def frame_pointer_key(camera_id: str) -> str:
    return f"frame_ptr:{camera_id}"


def camera_config_key(camera_id: str) -> str:
    return f"config:{camera_id}"


def camera_status_key(camera_id: str) -> str:
    return f"camera_status:{camera_id}"


def telemetry_channel(camera_id: str) -> str:
    return f"telemetry:{camera_id}"


def telemetry_latest_key(camera_id: str) -> str:
    return f"telemetry:latest:{camera_id}"


def incident_channel(camera_id: str) -> str:
    return f"incidents:{camera_id}"


def reid_embedding_key(global_id: str) -> str:
    return f"{REID_EMBEDDING_PREFIX}{global_id}"
