"""
InferencePipeline — D1→D5 orchestrator.
Moves from services.inference.pipeline → services.inference.ml.pipeline
"""
from __future__ import annotations

import asyncio
import time

import numpy as np
import redis.asyncio as aioredis

from libs.shared.core.settings import get_settings
from services.inference.ml.engines.person_detector import PersonDetector
from services.inference.ml.engines.item_detector import ItemDetector
from services.inference.ml.engines.background_blur import BackgroundBlur
from services.inference.services.tracker import PersonTracker
from services.inference.services.interaction import ItemInteractionDetector
from services.inference.ml.engines.shoplifting_model import ShopliftingModel
from services.inference.services.temporal_buffer import TemporalBuffer
from services.inference.utils.metrics import (
    frames_dropped, frames_processed, inference_latency, update_gpu_memory,
)
from libs.shared.logging.logger import get_logger
from libs.shared.shm.ring_buffer import RingBufferReader
from libs.shared.types.models import FramePointer

log = get_logger(__name__)


class InferencePipeline:
    """Orchestrates D1-D5 inference stages per frame."""

    def __init__(self) -> None:
        cfg = get_settings()
        self._cfg = cfg
        self._detector: PersonDetector | None = None
        self._item_detector: ItemDetector | None = None
        self._blur: BackgroundBlur | None = None
        self._tracker: PersonTracker | None = None
        self._interaction: ItemInteractionDetector | None = None
        self._classifier: ShopliftingModel | None = None
        self._buffer: TemporalBuffer | None = None

    async def load_models(self) -> None:
        cfg = self._cfg
        # Use specific engines for person and item detection
        self._detector = PersonDetector(cfg.person_detector_engine, cfg.model_backend)
        self._item_detector = ItemDetector(cfg.item_detector_engine, cfg.model_backend)
        self._blur = BackgroundBlur()
        self._tracker = PersonTracker()
        self._interaction = ItemInteractionDetector(
            hand_dist_px=cfg.hand_dist_px,
            interaction_frames=cfg.interaction_frames,
        )
        self._classifier = ShopliftingModel(cfg.model_engine_path, cfg.model_backend, cfg.temporal_window)
        self._buffer = TemporalBuffer(maxlen=cfg.temporal_window)
        log.info("Models loaded", extra={"device": cfg.model_backend})

    async def process(self, payload: bytes, redis: aioredis.Redis) -> None:
        t0 = time.perf_counter()
        try:
            ptr = FramePointer.from_bytes(payload)
            from libs.shared.shm.ring_buffer import ReaderCache
            reader = ReaderCache.get_reader(ptr.camera_id, 32, 720, 1280)
            frame = reader.read(ptr.slot_id)
        except Exception as exc:
            log.warning("Frame read failed", extra={"error": str(exc)})
            frames_dropped.inc()
            return

        if not self._detector or not self._item_detector:
            log.warning("Skipping frame: Model(s) not loaded")
            return
        
        if not self._classifier:
            # We can still track even if classifier is missing, but log it
            log.debug("Classifier not loaded, will skip shoplifting detection")

        # D1 — Person detection + segmentation
        detections, masks = self._detector.detect(frame)

        # D2 — Background blur
        frame_out = self._blur.apply(frame, masks)

        # D3 — Tracking
        tracks = self._tracker.update(detections)

        # D4 — Item interaction
        item_detections = self._item_detector.detect(frame)
        self._interaction.update(tracks, item_detections)
        self._interaction.delete_stale_tracks()

        # Build detailed detection message for UI
        ui_detections = []
        for track in tracks:
            ui_detections.append({
                "bbox": track["bbox"],
                "label": "person",
                "confidence": 1.0, 
                "track_id": track["id"]
            })
        
        for det in item_detections:
             ui_detections.append({
                "bbox": det["bbox"],
                "label": "item",
                "confidence": det["conf"],
                "track_id": None
            })

        # D5 — Temporal classification trigger (Asynchronous/Non-blocking)
        self._buffer.push(frame_out)
        if self._classifier and self._interaction.should_classify():
            # Check if we are already classifying for this camera to avoid overload
            if not hasattr(self, "_active_tasks"):
                self._active_tasks = set()
            
            if ptr.camera_id not in self._active_tasks:
                clip = self._buffer.get_clip()
                task = asyncio.create_task(self._run_classification(ptr.camera_id, clip, redis))
                self._active_tasks.add(ptr.camera_id)
                # Task cleanup call
                task.add_done_callback(lambda t: self._active_tasks.remove(ptr.camera_id) if ptr.camera_id in self._active_tasks else None)

        # Publish all detections + classification to Redis
        import json
        payload_data = {
            "camera_id": ptr.camera_id,
            "ts": time.time(),
            "detections": ui_detections,
            "action": None # Live stream doesn't wait for classification
        }
        await redis.publish(f"detections:{ptr.camera_id}", json.dumps(payload_data))

        elapsed = time.perf_counter() - t0
        inference_latency.observe(elapsed)
        frames_processed.inc()
        update_gpu_memory()

    async def _run_classification(self, camera_id: str, clip: np.ndarray, redis: aioredis.Redis) -> None:
        """Background task for slow action classification."""
        try:
            label, conf = await self._classifier.classify(clip)
            result = {"label": label, "confidence": conf}
            log.info("Action classification complete", extra=result)
            
            # Publish alert if positive
            import json
            payload = {
                "camera_id": camera_id,
                "ts": time.time(),
                "detections": [], # Historical frames don't need bbox again for alerts
                "action": result
            }
            await redis.publish(f"detections:{camera_id}", json.dumps(payload))
            
            # If shoplifting, we might want to push to persistence or alerting queue
            if label == "shoplifting":
                 await redis.lpush("persistence_queue", json.dumps({
                     "camera_id": camera_id,
                     "event": "shoplifting",
                     "confidence": conf,
                     "ts": time.time()
                 }))
        except Exception as e:
            log.error("Background classification failed", extra={"error": str(e)})
