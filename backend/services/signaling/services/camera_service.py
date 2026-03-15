"""Camera service helpers for snapshots and live stream payloads."""
from __future__ import annotations

import asyncio
import json

import redis.asyncio as aioredis

from services.signaling.services.preview_service import grab_jpeg
from shared.core.settings import get_settings
from shared.logging.logger import get_logger
from shared.redis.keys import telemetry_latest_key
from shared.types.events import CameraMetadataMessage

log = get_logger(__name__)


async def grab_metadata(camera_id: str, redis: aioredis.Redis) -> dict:
    """Fetch latest telemetry state for a camera."""
    data = await redis.get(telemetry_latest_key(camera_id))
    if data:
        try:
            return json.loads(data)
        except Exception:
            pass
    return {"timestamp": None, "detections": [], "incident": None}


def build_stream_message(camera_id: str, jpeg: bytes, metadata: dict) -> dict:
    message = CameraMetadataMessage(
        camera_id=camera_id,
        trace_id=metadata.get("trace_id"),
        timestamp=metadata.get("timestamp"),
        detections=metadata.get("detections", []),
        incident=metadata.get("incident"),
        review_status=metadata.get("review_status", "unreviewed"),
        metadata=metadata.get("metadata", {}),
    )
    return message.model_dump(mode="json")


async def mjpeg_stream(redis: aioredis.Redis, camera_id: str):
    boundary = "frame"
    settings = get_settings()
    while True:
        jpeg = await grab_jpeg(redis, camera_id)
        if jpeg is not None:
            yield (
                b"--" + boundary.encode("ascii") + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(jpeg)).encode("ascii") + b"\r\n\r\n"
                + jpeg
                + b"\r\n"
            )
        await asyncio.sleep(1.0 / max(settings.preview_frame_rate, 1.0))
