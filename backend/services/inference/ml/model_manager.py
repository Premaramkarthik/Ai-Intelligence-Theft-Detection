"""
Singleton Manager for GPU Models.
Handles lazy loading, warm-ups, and GPU context sharing.
"""
from __future__ import annotations
import asyncio
import numpy as np
from shared.logging.logger import get_logger
from shared.core.settings import get_settings
from services.inference.ml.engines.person_detector import PersonDetector
from services.inference.ml.engines.item_detector import ItemDetector
from services.inference.ml.engines.shoplifting_model import ShopliftingModel

log = get_logger(__name__)

class ModelManager:
    _instance: ModelManager | None = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._cfg = get_settings()
        self._person_detector: PersonDetector | None = None
        self._item_detector: ItemDetector | None = None
        self._shoplifting_model: ShopliftingModel | None = None
        self._lock = asyncio.Lock()
        self._initialized = True

    async def get_person_detector(self) -> PersonDetector:
        async with self._lock:
            if self._person_detector is None:
                log.info("Lazy loading PersonDetector...")
                self._person_detector = PersonDetector(device=self._cfg.model_backend)
                await self._warmup(self._person_detector)
            return self._person_detector

    async def get_item_detector(self) -> ItemDetector:
        async with self._lock:
            if self._item_detector is None:
                log.info("Lazy loading ItemDetector...")
                self._item_detector = ItemDetector(device=self._cfg.model_backend)
                await self._warmup(self._item_detector)
            return self._item_detector

    async def get_shoplifting_model(self) -> ShopliftingModel:
        async with self._lock:
            if self._shoplifting_model is None:
                if not self._cfg.model_engine_path:
                    log.warning("Shoplifting model path not configured")
                    return None
                log.info("Lazy loading ShopliftingModel...")
                self._shoplifting_model = ShopliftingModel(
                    self._cfg.model_engine_path, 
                    self._cfg.model_backend, 
                    self._cfg.temporal_window
                )
                # Warmup for 3D CNN is slightly different (needs clip)
            return self._shoplifting_model

    async def _warmup(self, model) -> None:
        """Runs a dummy inference to initialize CUDA kernels."""
        try:
            # Create a black dummy frame
            dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            model.detect(dummy_frame)
            log.info(f"Warmup complete for {model.__class__.__name__}")
        except Exception as e:
            log.error(f"Warmup failed for {model.__class__.__name__}", extra={"error": str(e)})

    async def cleanup(self) -> None:
        """Explicitly clear model references for memory recovery."""
        async with self._lock:
            self._person_detector = None
            self._item_detector = None
            self._shoplifting_model = None
            log.info("ModelManager cleared GPU models")
