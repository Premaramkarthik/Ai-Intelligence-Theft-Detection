from unittest.mock import AsyncMock

import pytest

from shared.redis.frame_queue import dequeue_fair_frame, dequeue_frame, enqueue_frame
from shared.redis.keys import (
    camera_config_key,
    frame_pointer_key,
    frame_queue_key,
    incident_channel,
    telemetry_channel,
    telemetry_latest_key,
)


def test_redis_key_builders_are_centralized():
    assert frame_queue_key() == "frames"
    assert frame_queue_key("cam-1") == "frames:cam-1"
    assert frame_pointer_key("cam-1") == "frame_ptr:cam-1"
    assert camera_config_key("cam-1") == "config:cam-1"
    assert telemetry_channel("cam-1") == "telemetry:cam-1"
    assert telemetry_latest_key("cam-1") == "telemetry:latest:cam-1"
    assert incident_channel("cam-1") == "incidents:cam-1"


@pytest.mark.asyncio
async def test_enqueue_frame_writes_camera_queue_by_default():
    redis = AsyncMock()
    redis.llen.return_value = 0

    await enqueue_frame(redis, "cam-1", "payload", maxlen=5)

    redis.rpush.assert_awaited_once_with("frames:cam-1", "payload")


@pytest.mark.asyncio
async def test_dequeue_frame_uses_selected_queue():
    redis = AsyncMock()
    redis.blpop.return_value = ("frames:cam-1", "payload")

    queue_name, payload = await dequeue_frame(redis, timeout=1, camera_id="cam-1")

    redis.blpop.assert_awaited_once_with("frames:cam-1", timeout=1)
    assert queue_name == "frames:cam-1"
    assert payload == "payload"


@pytest.mark.asyncio
async def test_dequeue_fair_frame_round_robins_camera_queues():
    redis = AsyncMock()
    redis.lpop.side_effect = [None, "payload-cam-2"]

    item = await dequeue_fair_frame(redis, ["cam-1", "cam-2"], start_index=0, idle_sleep_s=0)

    assert item == ("cam-2", "payload-cam-2", 0)
