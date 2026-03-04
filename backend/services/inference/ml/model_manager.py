"""
Singleton Manager for GPU Models.
Handles lazy loading, warm-ups, TensorRT auto-detection, and GPU context sharing.
"""
from __future__ import annotations

import asyncio

from shared.logging.logger import get_logger
from shared.core.settings import get_settings
from services.inference.ml.engines.object_detector import ObjectDetector
from services.inference.ml.engines.shoplifting_model import ShopliftingModel

log = get_logger(__name__)


class ModelManager:
    _instance: ModelManager | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._cfg = get_settings()
        self._detector: ObjectDetector | None = None
        self._shoplifting_model: ShopliftingModel | None = None
        self._redis = None
        self._lock = asyncio.Lock()
        self._initialized = True

    @property
    def redis(self):
        """Shared async Redis client."""
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._cfg.redis_url, decode_responses=False)
        return self._redis

    def _detect_device(self) -> str:
        try:
            import cv2
            if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                return self._cfg.model_backend
        except Exception:
            pass
        try:
            import pynvml
            pynvml.nvmlInit()
            if pynvml.nvmlDeviceGetCount() > 0:
                pynvml.nvmlShutdown()
                return self._cfg.model_backend
        except Exception:
            pass
        log.warning("No GPU detected, falling back to CPU")
        return "cpu"

    async def preload_all(self) -> None:
        device = self._detect_device()
        log.info(f"Targeting inference device: {device}")
        await asyncio.gather(
            self.get_detector(device=device),
            self.get_shoplifting_model(device=device),
        )
        # Warmup detector after loading
        if self._detector:
            await asyncio.to_thread(self._detector.warmup)
        log.info("All models loaded and warmed up")

    async def get_detector(self, device: str | None = None) -> ObjectDetector:
        async with self._lock:
            if self._detector is None:
                target = device or self._detect_device()
                log.info(f"Loading ObjectDetector on {target}...")
                self._detector = ObjectDetector(device=target)
            return self._detector

    async def get_shoplifting_model(self, device: str | None = None) -> ShopliftingModel | None:
        async with self._lock:
            if self._shoplifting_model is None:
                if not self._cfg.model_engine_path:
                    log.warning("Shoplifting model path not configured")
                    return None
                target = device or self._detect_device()
                log.info(f"Loading ShopliftingModel on {target}...")
                self._shoplifting_model = ShopliftingModel(
                    self._cfg.model_engine_path, target, self._cfg.temporal_window
                )
            return self._shoplifting_model

    async def cleanup(self) -> None:
        async with self._lock:
            self._detector = None
            self._shoplifting_model = None
            log.info("ModelManager cleared GPU models")
