"""
Singleton manager for the fixed detector and behavior-classifier engines.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from services.inference.ml.engines.behavior_classifier import BehaviorClassifier
from shared.logging.logger import get_logger
from shared.core.settings import get_settings
from services.inference.ml.engines.object_detector import ObjectDetector

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
        self._behavior_classifier: BehaviorClassifier | None = None
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
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"

    @staticmethod
    def _fallback_onnx_path(model_path: str) -> str:
        path = Path(model_path)
        return str(path.with_suffix(".onnx"))

    def _resolve_detector_path(self, device: str) -> str:
        path = self._cfg.detector_engine_path
        if device == "cuda":
            return path
        fallback = self._fallback_onnx_path(path)
        if not Path(fallback).exists():
            raise RuntimeError(
                "CUDA is unavailable and detector ONNX fallback is missing: "
                f"{fallback}"
            )
        return fallback

    def _resolve_classifier_path(self, device: str) -> str:
        path = self._cfg.classifier_engine_path
        if device == "cuda":
            return path
        fallback = self._fallback_onnx_path(path)
        if not Path(fallback).exists():
            raise RuntimeError(
                "CUDA is unavailable and classifier ONNX fallback is missing: "
                f"{fallback}"
            )
        return fallback

    async def preload_all(self) -> None:
        device = self._detect_device()
        log.info(f"Targeting inference device: {device}")
        await asyncio.gather(
            self.get_detector(device=device),
            self.get_behavior_classifier(device=device),
        )
        if self._detector:
            await asyncio.to_thread(self._detector.warmup)
        log.info("All models loaded and warmed up")

    async def get_detector(self, device: str | None = None) -> ObjectDetector:
        async with self._lock:
            if self._detector is None:
                target = device or self._detect_device()
                model_path = self._resolve_detector_path(target)
                log.info("Loading ObjectDetector", extra={"device": target, "path": model_path})
                self._detector = ObjectDetector(model_path, device=target)
            return self._detector

    async def get_behavior_classifier(self, device: str | None = None) -> BehaviorClassifier:
        async with self._lock:
            if self._behavior_classifier is None:
                target = device or self._detect_device()
                model_path = self._resolve_classifier_path(target)
                log.info("Loading BehaviorClassifier", extra={"device": target, "path": model_path})
                self._behavior_classifier = BehaviorClassifier(
                    model_path, target, self._cfg.temporal_window
                )
            return self._behavior_classifier

    async def cleanup(self) -> None:
        async with self._lock:
            self._detector = None
            self._behavior_classifier = None
            log.info("ModelManager cleared GPU models")
