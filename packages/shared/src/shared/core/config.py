"""
ConfigManager — polls Redis for live camera config updates.
Moved from shared.config.config_manager → shared.core.config
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field

import redis.asyncio as aioredis

from shared.core.settings import get_settings
from shared.logging.logger import get_logger

log = get_logger(__name__)

_cfg = get_settings()
POLL_INTERVAL_S: float = _cfg.config_poll_interval_s


@dataclass
class CameraConfig:
    camera_id: str
    roi: dict = field(default_factory=dict)
    confidence_threshold: float = 0.45
    iou_threshold: float = 0.15
    hand_dist_px: int = 80
    min_displacement_px: int = 30
    interaction_frames: int = 5
    enabled: bool = True


class ConfigManager:
    """Reads live camera config from Redis hash config:<camera_id>."""

    def __init__(self, redis_url: str) -> None:
        self._url = redis_url
        self._configs: dict[str, CameraConfig] = {}
        self._redis: aioredis.Redis | None = None

    async def start(self) -> None:
        self._redis = aioredis.from_url(self._url, decode_responses=True)
        log.info("ConfigManager started", extra={"redis": self._url})

    async def stop(self) -> None:
        if self._redis:
            await self._redis.aclose()

    async def poll_loop(self) -> None:
        while True:
            await asyncio.sleep(POLL_INTERVAL_S)
            await self._refresh_all()

    async def _refresh_all(self) -> None:
        if not self._redis:
            return
        try:
            keys = await self._redis.keys("config:*")
            for key in keys:
                camera_id = key.split(":", 1)[1]
                raw = await self._redis.hgetall(key)
                self._configs[camera_id] = self._parse(camera_id, raw)
        except Exception as exc:
            log.warning("Config poll failed", extra={"error": str(exc)})

    @staticmethod
    def _parse(camera_id: str, raw: dict) -> CameraConfig:
        return CameraConfig(
            camera_id=camera_id,
            roi=json.loads(raw.get("roi", "{}")),
            confidence_threshold=float(raw.get("confidence_threshold", 0.45)),
            iou_threshold=float(raw.get("iou_threshold", 0.15)),
            hand_dist_px=int(raw.get("hand_dist_px", 80)),
            min_displacement_px=int(raw.get("min_displacement_px", 30)),
            interaction_frames=int(raw.get("interaction_frames", 5)),
            enabled=raw.get("enabled", "true").lower() == "true",
        )

    def get(self, camera_id: str) -> CameraConfig:
        return self._configs.get(camera_id, CameraConfig(camera_id=camera_id))

    async def set(self, camera_id: str, cfg: CameraConfig) -> None:
        if not self._redis:
            raise RuntimeError("ConfigManager not started")
        data = {
            "roi": json.dumps(cfg.roi),
            "confidence_threshold": str(cfg.confidence_threshold),
            "iou_threshold": str(cfg.iou_threshold),
            "hand_dist_px": str(cfg.hand_dist_px),
            "min_displacement_px": str(cfg.min_displacement_px),
            "interaction_frames": str(cfg.interaction_frames),
            "enabled": str(cfg.enabled).lower(),
        }
        await self._redis.hset(f"config:{camera_id}", mapping=data)
        self._configs[camera_id] = cfg
        log.info("Config updated", extra={"camera_id": camera_id})
