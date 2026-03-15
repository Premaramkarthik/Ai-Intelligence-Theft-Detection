from __future__ import annotations

import asyncio
from fractions import Fraction

from aiortc import MediaStreamTrack
from av import VideoFrame
import redis.asyncio as aioredis

from services.signaling.services.preview_service import grab_frame
from shared.core.settings import get_settings


class CameraVideoTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, redis: aioredis.Redis, camera_id: str):
        super().__init__()
        self._redis = redis
        self._camera_id = camera_id
        self._settings = get_settings()
        self._frame_interval = 1.0 / max(self._settings.preview_frame_rate, 1.0)

    async def recv(self) -> VideoFrame:
        pts, time_base = await self.next_timestamp()
        frame = await grab_frame(self._redis, self._camera_id)
        while frame is None:
            await asyncio.sleep(self._frame_interval)
            frame = await grab_frame(self._redis, self._camera_id)

        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts = pts
        video_frame.time_base = time_base or Fraction(1, 90000)
        await asyncio.sleep(self._frame_interval)
        return video_frame

