"""
ConfigManager — polls Redis for live camera config updates.
Moved from shared.config.config_manager → shared.core.config
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import redis.asyncio as aioredis

from shared.core.settings import get_settings
from shared.logging.logger import get_logger
from shared.redis.keys import CONFIG_KEY_PATTERN, camera_config_key

log = get_logger(__name__)

_cfg = get_settings()
POLL_INTERVAL_S: float = _cfg.config_poll_interval_s


@dataclass
class CameraConfig:
    camera_id: str
    organization_id: str = _cfg.default_organization_id
    store_id: str = _cfg.default_store_id
    roi: dict = field(default_factory=dict)
    confidence_threshold: float = 0.45
    iou_threshold: float = 0.15
    hand_dist_px: int = 80
    min_displacement_px: int = 30
    interaction_frames: int = 5
    enabled: bool = True
    loaded_at: float = 0.0


def parse_camera_config(camera_id: str, raw: dict, *, loaded_at: float = 0.0) -> CameraConfig:
    return CameraConfig(
        camera_id=camera_id,
        organization_id=raw.get("organization_id", _cfg.default_organization_id),
        store_id=raw.get("store_id", _cfg.default_store_id),
        roi=json.loads(raw.get("roi", "{}")),
        confidence_threshold=float(raw.get("confidence_threshold", _cfg.default_confidence_threshold)),
        iou_threshold=float(raw.get("iou_threshold", 0.15)),
        hand_dist_px=int(raw.get("hand_dist_px", _cfg.hand_dist_px)),
        min_displacement_px=int(raw.get("min_displacement_px", 30)),
        interaction_frames=int(raw.get("interaction_frames", _cfg.interaction_frames)),
        enabled=raw.get("enabled", "true").lower() == "true",
        loaded_at=loaded_at,
    )


def camera_config_mapping(cfg: CameraConfig) -> dict[str, str]:
    return {
        "roi": json.dumps(cfg.roi),
        "organization_id": cfg.organization_id,
        "store_id": cfg.store_id,
        "confidence_threshold": str(cfg.confidence_threshold),
        "iou_threshold": str(cfg.iou_threshold),
        "hand_dist_px": str(cfg.hand_dist_px),
        "min_displacement_px": str(cfg.min_displacement_px),
        "interaction_frames": str(cfg.interaction_frames),
        "enabled": str(cfg.enabled).lower(),
    }


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
            keys = await self._redis.keys(CONFIG_KEY_PATTERN)
            for key in keys:
                camera_id = key.split(":", 1)[1]
                raw = await self._redis.hgetall(key)
                self._configs[camera_id] = self._parse(camera_id, raw)
        except Exception as exc:
            log.warning("Config poll failed", extra={"error": str(exc)})

    @staticmethod
    def _parse(camera_id: str, raw: dict) -> CameraConfig:
        return parse_camera_config(camera_id, raw)

    def get(self, camera_id: str) -> CameraConfig:
        return self._configs.get(camera_id, CameraConfig(camera_id=camera_id))

    async def set(self, camera_id: str, cfg: CameraConfig) -> None:
        if not self._redis:
            raise RuntimeError("ConfigManager not started")
        await self._redis.hset(camera_config_key(camera_id), mapping=camera_config_mapping(cfg))
        self._configs[camera_id] = cfg
        log.info("Config updated", extra={"camera_id": camera_id})
