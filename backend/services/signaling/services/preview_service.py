"""Shared preview helpers used by MJPEG and WebRTC paths."""
from __future__ import annotations

import cv2
import redis.asyncio as aioredis

from services.signaling.utils.metrics import snapshot_failures
from shared.core.settings import get_settings
from shared.logging.logger import get_logger
from shared.redis.keys import frame_pointer_key
from shared.types.models import FramePointer

log = get_logger(__name__)


async def grab_frame(redis: aioredis.Redis, camera_id: str):
    settings = get_settings()
    try:
        raw = await redis.get(frame_pointer_key(camera_id))
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
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif frame.ndim == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        return frame
    except Exception as exc:
        if "Stale frame pointer" in str(exc):
            await redis.delete(frame_pointer_key(camera_id))
        snapshot_failures.labels(camera_id=camera_id).inc()
        log.warning("Failed to grab preview frame", extra={"camera_id": camera_id, "error": str(exc)})
        return None


async def grab_jpeg(redis: aioredis.Redis, camera_id: str) -> bytes | None:
    frame = await grab_frame(redis, camera_id)
    if frame is None:
        return None
    ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        snapshot_failures.labels(camera_id=camera_id).inc()
        return None
    return jpeg.tobytes()

