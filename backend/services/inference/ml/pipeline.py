"""
InferencePipeline — D1→D5 orchestrator.
Moves from services.inference.pipeline → services.inference.ml.pipeline
"""
from __future__ import annotations

import asyncio
import time

import numpy as np
import redis.asyncio as aioredis

from shared.core.settings import get_settings
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
from shared.logging.logger import get_logger
from shared.shm.ring_buffer import RingBufferReader
from shared.types.models import FramePointer
from services.inference.ml.model_manager import ModelManager

log = get_logger(__name__)


class InferencePipeline:
    """Orchestrates D1-D5 inference stages per frame."""

    def __init__(self) -> None:
        cfg = get_settings()
        self._cfg = cfg
        self._models = ModelManager()
        self._blur: BackgroundBlur | None = None
        self._tracker: PersonTracker | None = None
        self._interaction: ItemInteractionDetector | None = None
        self._buffer: TemporalBuffer | None = None
        self._active_tasks: set[str] = set()

    async def load_models(self) -> None:
        """Initializes non-GPU heavy components."""
        cfg = self._cfg
        self._blur = BackgroundBlur()
        self._tracker = PersonTracker()
        self._interaction = ItemInteractionDetector(
            hand_dist_px=cfg.hand_dist_px,
            interaction_frames=cfg.interaction_frames,
        )
        self._buffer = TemporalBuffer(maxlen=cfg.temporal_window)
        log.info("Pipeline components initialized (GPU models on lazy-load)")

    async def process(self, payload: bytes, redis: aioredis.Redis) -> None:
        t0 = time.perf_counter()
        try:
            ptr = FramePointer.from_bytes(payload)
            from shared.shm.ring_buffer import ReaderCache
            reader = ReaderCache.get_reader(ptr.camera_id, 32, 720, 1280)
            frame = reader.read(ptr.slot_id)
        except Exception as exc:
            log.warning("Frame read failed", extra={"error": str(exc)})
            frames_dropped.inc()
            return

        # Get models lazily
        person_detector = await self._models.get_person_detector()
        item_detector = await self._models.get_item_detector()
        
        if not person_detector or not item_detector:
            log.warning("Skipping frame: Model(s) not available")
            return

        # D1 — Person detection + segmentation
        detections, masks = person_detector.detect(frame)

        # D2 — Background blur
        frame_out = self._blur.apply(frame, masks)

        # D3 — Tracking
        tracks = self._tracker.update(detections)

        # D4 — Item interaction
        item_detections = item_detector.detect(frame)
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

        # D5 — Temporal classification trigger
        self._buffer.push(frame_out)
        classifier = await self._models.get_shoplifting_model()
        
        if classifier and self._interaction.should_classify():
            if ptr.camera_id not in self._active_tasks:
                clip = self._buffer.get_clip()
                task = asyncio.create_task(self._run_classification(ptr.camera_id, clip, redis, classifier))
                self._active_tasks.add(ptr.camera_id)
                task.add_done_callback(lambda t: self._active_tasks.remove(ptr.camera_id) if ptr.camera_id in self._active_tasks else None)

        # Publish results
        import json
        payload_data = {
            "camera_id": ptr.camera_id,
            "ts": time.time(),
            "detections": ui_detections,
            "action": None
        }
        await redis.publish(f"detections:{ptr.camera_id}", json.dumps(payload_data))

        elapsed = time.perf_counter() - t0
        inference_latency.observe(elapsed)
        frames_processed.inc()
        update_gpu_memory()

    async def _run_classification(self, camera_id: str, clip: np.ndarray, redis: aioredis.Redis, classifier: ShopliftingModel) -> None:
        """Background task for slow action classification."""
        try:
            label, conf = await classifier.classify(clip)
            result = {"label": label, "confidence": conf}
            log.info("Action classification complete", extra=result)
            
            import json
            payload = {
                "camera_id": camera_id,
                "ts": time.time(),
                "detections": [],
                "action": result
            }
            await redis.publish(f"detections:{camera_id}", json.dumps(payload))
            
            if label == "shoplifting":
                  await redis.lpush("persistence_queue", json.dumps({
                      "camera_id": camera_id,
                      "event": "shoplifting",
                      "confidence": conf,
                      "ts": time.time()
                  }))
        except Exception as e:
            log.error("Background classification failed", extra={"error": str(e)})
