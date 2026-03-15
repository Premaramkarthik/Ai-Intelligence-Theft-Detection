from __future__ import annotations

import redis.asyncio as aioredis

from shared.core.settings import Settings
from shared.redis.keys import frame_pointer_key
from shared.types.models import FramePointer


class FrameInput:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def read(self, payload: bytes | str, redis: aioredis.Redis) -> tuple[FramePointer, object]:
        payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload
        ptr = FramePointer.from_bytes(payload_bytes)
        from shared.shm.ring_buffer import ReaderCache

        reader = ReaderCache.get_reader(
            ptr.camera_id,
            self._settings.shm_slots_per_cam,
            self._settings.frame_height,
            self._settings.frame_width,
        )
        frame = reader.read(ptr.slot_id, expected_generation=ptr.generation)
        return ptr, frame

    async def cleanup_stale_pointer(self, ptr: FramePointer | None, redis: aioredis.Redis) -> None:
        if ptr is None:
            return
        latest = await redis.get(frame_pointer_key(ptr.camera_id))
        if not latest:
            return
        latest_ptr = FramePointer.from_bytes(latest.encode("utf-8"))
        if (
            latest_ptr.camera_id == ptr.camera_id
            and latest_ptr.slot_id == ptr.slot_id
            and latest_ptr.generation == ptr.generation
        ):
            await redis.delete(frame_pointer_key(ptr.camera_id))
