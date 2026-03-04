"""Camera service — reads raw frame from SHM and returns JPEG bytes."""
from __future__ import annotations

import struct

import cv2
import numpy as np
import redis.asyncio as aioredis

from shared.logging.logger import get_logger
from shared.shm.ring_buffer import RingBufferReader
from shared.core.settings import get_settings

log = get_logger(__name__)


async def grab_jpeg(redis: aioredis.Redis, camera_id: str) -> bytes | None:
    """Read latest frame pointer from Redis, decode from SHM, return JPEG."""
    settings = get_settings()
    try:
        raw = await redis.get(f"frame_ptr:{camera_id}")
        if raw is None:
            return None
        slot_idx = int(raw)
        from shared.shm.ring_buffer import ReaderCache
        reader = ReaderCache.get_reader(
            camera_id,
            settings.shm_slots_per_cam,
            settings.frame_height,
            settings.frame_width,
        )
        frame = reader.read(slot_idx)
        if frame is None or frame.size == 0:
            return None
            
        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return jpeg.tobytes()
    except Exception as exc:
        log.warning("Failed to grab JPEG", extra={"camera_id": camera_id, "error": str(exc)})
        return None
