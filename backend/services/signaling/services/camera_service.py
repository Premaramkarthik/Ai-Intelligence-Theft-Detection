"""Camera service helpers for snapshots and live stream payloads."""
from __future__ import annotations

import base64
import json

import cv2
import redis.asyncio as aioredis

from shared.core.settings import get_settings
from shared.logging.logger import get_logger
from shared.types.events import CameraStreamMessage
from shared.types.models import FramePointer

log = get_logger(__name__)


async def grab_jpeg(redis: aioredis.Redis, camera_id: str) -> bytes | None:
    """Read the latest frame pointer from Redis, decode from SHM, and return JPEG bytes."""
    settings = get_settings()
    try:
        raw = await redis.get(f"frame_ptr:{camera_id}")
        if raw is None:
            return None

        ptr = FramePointer.from_bytes(raw.encode("utf-8"))
        from shared.shm.ring_buffer import ReaderCache

        reader = ReaderCache.get_reader(
            camera_id,
            settings.shm_slots_per_cam,
            settings.frame_height,
            settings.frame_width,
        )
        frame = reader.read(ptr.slot_id, expected_generation=ptr.generation)
        if frame.size == 0:
            return None

        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return None
        return jpeg.tobytes()
    except Exception as exc:
        log.warning("Failed to grab JPEG", extra={"camera_id": camera_id, "error": str(exc)})
        return None


async def grab_metadata(camera_id: str, redis: aioredis.Redis) -> dict:
    """Fetch latest telemetry state for a camera."""
    data = await redis.get(f"telemetry:latest:{camera_id}")
    if data:
        try:
            return json.loads(data)
        except Exception:
            pass
    return {"timestamp": None, "detections": [], "incident": None}


def build_stream_message(camera_id: str, jpeg: bytes, metadata: dict) -> dict:
    message = CameraStreamMessage(
        camera_id=camera_id,
        timestamp=metadata.get("timestamp"),
        image_jpeg_base64=base64.b64encode(jpeg).decode("ascii"),
        detections=metadata.get("detections", []),
        incident=metadata.get("incident"),
    )
    return message.model_dump(mode="json")
