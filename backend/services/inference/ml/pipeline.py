"""
InferencePipeline — D1→D5 orchestrator.

Uses a SINGLE shared ObjectDetector for all cameras.
Per-camera tracker state is isolated via tracker_id parameter.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

import numpy as np
import redis.asyncio as aioredis

from shared.core.settings import get_settings
from shared.logging.logger import get_logger
from shared.types.models import FramePointer
from services.inference.ml.engines.background_blur import BackgroundBlur
from services.inference.ml.engines.shoplifting_model import ShopliftingModel
from services.inference.ml.model_manager import ModelManager
from services.inference.services.interaction import ItemInteractionDetector
from services.inference.services.temporal_buffer import TemporalBuffer
from services.inference.services.reid_service import ReIDService
from services.inference.utils.metrics import (
    frames_dropped, frames_processed, inference_latency, update_gpu_memory,
)

log = get_logger(__name__)

DEFAULT_SKIP_N = 3
MIN_SKIP = 1
MAX_SKIP = 10
FAST_THRESHOLD = 0.020   # 20ms
SLOW_THRESHOLD = 0.050   # 50ms
PREDICTION_STREAM = "stream:predictions"
STREAM_MAXLEN = 10000  # Trim stream to prevent unbounded growth


class InferencePipeline:
    """Orchestrates D1-D5 inference stages per frame."""

    def __init__(self) -> None:
        cfg = get_settings()
        self._cfg = cfg
        self._models = ModelManager()
        self._blur: BackgroundBlur | None = None
        self._interaction: ItemInteractionDetector | None = None
        self._buffer: TemporalBuffer | None = None
        self._reid: ReIDService | None = None
        self._active_tasks: set[str] = set()

        self._frame_count = 0
        self._skip_n = DEFAULT_SKIP_N
        self._last_persons: list = []
        self._last_masks: list = []
        self._last_items: list = []
        self._last_tracks: list = []
        self._last_actions: dict[str, dict] = {}

    async def load_models(self) -> None:
        cfg = self._cfg
        self._blur = BackgroundBlur()
        self._interaction = ItemInteractionDetector(
            hand_dist_px=cfg.hand_dist_px,
            interaction_frames=cfg.interaction_frames,
        )
        self._buffer = TemporalBuffer(maxlen=cfg.temporal_window)
        self._reid = ReIDService(self._models.redis)
        await self._models.preload_all()
        log.info("Pipeline ready — models preloaded and warmed up")

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

        detector = await self._models.get_detector()
        if not detector:
            return

        # D1 + D4 — single-pass detection with adaptive frame skip
        if self._frame_count % self._skip_n == 0:
            result = detector.detect_and_track(frame, tracker_id=ptr.camera_id)

            self._last_persons = result.person_boxes
            self._last_masks = result.person_masks
            self._last_items = result.items
            self._last_tracks = [
                {"bbox": bbox, "id": result.track_ids[i] if i < len(result.track_ids) else i + 1}
                for i, bbox in enumerate(result.person_boxes)
            ]

        masks = self._last_masks
        item_detections = self._last_items
        tracks = self._last_tracks
        self._frame_count += 1

        # D2 — Background blur
        frame_out = self._blur.apply(frame, masks)

        # Cross-Camera Re-ID (run feature extraction off-thread)
        if self._reid:
            for track in tracks:
                if not str(track["id"]).startswith("global_") or self._frame_count % 100 == 0:
                    try:
                        bbox = [int(v) for v in track["bbox"]]
                        x1, y1 = max(0, bbox[0]), max(0, bbox[1])
                        x2, y2 = min(frame.shape[1], bbox[2]), min(frame.shape[0], bbox[3])
                        if y2 > y1 and x2 > x1:
                            crop = frame[y1:y2, x1:x2]
                            embedding = await asyncio.to_thread(
                                self._reid.extract_features, crop
                            )
                            global_id = await self._reid.get_global_id(embedding)
                            if global_id:
                                track["id"] = f"global_{global_id}"
                            else:
                                new_id = str(uuid.uuid4())[:8]
                                await self._reid.register_track(new_id, embedding)
                                track["id"] = f"global_{new_id}"
                    except Exception as e:
                        log.error("Re-ID failed", extra={"error": str(e)})

        # D4 — Item interaction
        self._interaction.update(tracks, item_detections)
        self._interaction.delete_stale_tracks()

        # Build UI payload
        cached_action = self._last_actions.get(ptr.camera_id, {"label": "normal", "confidence": 1.0})
        ui_detections = [
            {
                "bbox": t["bbox"],
                "label": cached_action["label"],
                "confidence": cached_action["confidence"],
                "track_id": t["id"],
            }
            for t in tracks
        ]
        ui_detections.extend(
            {
                "bbox": det["bbox"],
                "label": det["label"],
                "confidence": det["conf"],
                "track_id": None,
            }
            for det in item_detections
        )

        # D5 — Temporal classification trigger
        self._buffer.push(frame_out)
        classifier = await self._models.get_shoplifting_model()

        if classifier and self._interaction.should_classify():
            if ptr.camera_id not in self._active_tasks:
                clip = self._buffer.get_clip()
                task = asyncio.create_task(self._run_classification(ptr.camera_id, clip, redis, classifier))
                self._active_tasks.add(ptr.camera_id)
                task.add_done_callback(
                    lambda t, cid=ptr.camera_id: self._active_tasks.discard(cid)
                )

        # Publish results
        payload_data = {
            "camera_id": ptr.camera_id,
            "ts": time.time(),
            "detections": ui_detections,
            "action": None,
        }
        payload_json = json.dumps(payload_data)
        # Pub/Sub for real-time WebSocket consumers
        await redis.publish(f"detections:{ptr.camera_id}", payload_json)
        await redis.set(f"detections:latest:{ptr.camera_id}", payload_json)
        # Redis Stream for alerting + persistence (guaranteed delivery)
        await redis.xadd(
            PREDICTION_STREAM,
            {"payload": payload_json},
            maxlen=STREAM_MAXLEN,
        )

        elapsed = time.perf_counter() - t0
        inference_latency.observe(elapsed)
        frames_processed.inc()
        update_gpu_memory()

        # Adaptive frame skip
        if elapsed > SLOW_THRESHOLD:
            self._skip_n = min(self._skip_n + 1, MAX_SKIP)
        elif elapsed < FAST_THRESHOLD:
            self._skip_n = max(self._skip_n - 1, MIN_SKIP)

    async def _run_classification(
        self, camera_id: str, clip: list[np.ndarray], redis: aioredis.Redis, classifier: ShopliftingModel
    ) -> None:
        try:
            label, conf = await classifier.classify(clip)
            result = {"label": label, "confidence": conf}
            self._last_actions[camera_id] = result

            current_raw = await redis.get(f"detections:latest:{camera_id}")
            if current_raw:
                current = json.loads(current_raw)
                current["action"] = result
                current["ts"] = time.time()
                await redis.set(f"detections:latest:{camera_id}", json.dumps(current))

            payload = {"camera_id": camera_id, "ts": time.time(), "detections": [], "action": result}
            payload_json = json.dumps(payload)
            await redis.publish(f"detections:{camera_id}", payload_json)
            # Stream for alerting + persistence
            await redis.xadd(
                PREDICTION_STREAM,
                {"payload": payload_json},
                maxlen=STREAM_MAXLEN,
            )
        except Exception as e:
            log.error("Classification failed", extra={"error": str(e)})
