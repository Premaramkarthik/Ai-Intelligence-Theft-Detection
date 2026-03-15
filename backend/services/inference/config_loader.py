from __future__ import annotations

import time

import redis.asyncio as aioredis

from services.inference.runtime import CameraRuntimeState
from shared.core.config import CameraConfig, parse_camera_config
from shared.core.settings import Settings
from shared.redis.keys import camera_config_key


class InferenceConfigLoader:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def load(
        self,
        camera_id: str,
        redis: aioredis.Redis,
        state: CameraRuntimeState,
    ) -> CameraConfig:
        now = time.time()
        if state.config and now - state.config.loaded_at < self._settings.config_poll_interval_s:
            return state.config

        raw = await redis.hgetall(camera_config_key(camera_id))
        config = parse_camera_config(
            camera_id,
            raw,
            loaded_at=now,
        )
        state.interaction.configure(
            hand_dist_px=config.hand_dist_px,
            interaction_frames=config.interaction_frames,
        )
        state.config = config
        return config
