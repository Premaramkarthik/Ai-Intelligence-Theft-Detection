from __future__ import annotations

import asyncio
import time

import redis.asyncio as aioredis

from shared.core.settings import get_settings
from shared.redis.keys import CAMERA_SOURCES_KEY
from shared.redis.keys import frame_queue_key
from shared.types.models import FramePointer

_cfg = get_settings()


async def enqueue_frame(
    redis: aioredis.Redis,
    camera_id: str,
    payload: str,
    maxlen: int,
) -> None:
    camera_queue = frame_queue_key(camera_id)
    queue_names = [camera_queue]
    if _cfg.legacy_global_frame_queue:
        queue_names.append(frame_queue_key())

    for queue_name in queue_names:
        queue_len = await redis.llen(queue_name)
        if queue_len >= maxlen:
            await redis.lpop(queue_name)
        await redis.rpush(queue_name, payload)


async def dequeue_frame(
    redis: aioredis.Redis,
    timeout: int = 1,
    camera_id: str | None = None,
) -> tuple[str, bytes | str] | None:
    queue_name = frame_queue_key(camera_id)
    item = await redis.blpop(queue_name, timeout=timeout)
    if item is None:
        return None
    key, payload = item
    decoded_key = key.decode("utf-8") if isinstance(key, bytes) else key
    return decoded_key, payload


async def list_camera_queues(redis: aioredis.Redis) -> list[str]:
    sources = await redis.hkeys(CAMERA_SOURCES_KEY)
    return [source.decode("utf-8") if isinstance(source, bytes) else source for source in sources]


async def dequeue_fair_frame(
    redis: aioredis.Redis,
    camera_ids: list[str],
    *,
    start_index: int = 0,
    idle_sleep_s: float = 0.1,
) -> tuple[str, bytes | str, int] | None:
    if not camera_ids:
        await asyncio.sleep(idle_sleep_s)
        return None

    total = len(camera_ids)
    for offset in range(total):
        index = (start_index + offset) % total
        camera_id = camera_ids[index]
        payload = await redis.lpop(frame_queue_key(camera_id))
        if payload is not None:
            return camera_id, payload, (index + 1) % total

    await asyncio.sleep(idle_sleep_s)
    return None


def frame_age_seconds(payload: bytes | str) -> float:
    raw = payload if isinstance(payload, bytes) else payload.encode("utf-8")
    ptr = FramePointer.from_bytes(raw)
    return max(0.0, time.time() - ptr.t_capture)
