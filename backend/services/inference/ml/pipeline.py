"""
Inference pipeline orchestration with focused collaborators.
"""
from __future__ import annotations

import asyncio
import time

import numpy as np
import redis.asyncio as aioredis

from services.inference.config_loader import InferenceConfigLoader
from services.inference.evidence import save_evidence_frame
from services.inference.frame_input import FrameInput
from services.inference.ml.engines.behavior_classifier import BehaviorClassifier
from services.inference.ml.model_manager import ModelManager
from services.inference.publishers import IncidentPublisher, TelemetryPublisher
from services.inference.runtime import CameraRuntimeState, CameraStateStore
from services.inference.services.reid_service import ReIDService
from services.inference.utils.metrics import (
    classification_attempts,
    classification_failures,
    detector_failures,
    frames_dropped,
    frames_processed,
    incidents_emitted,
    inference_latency,
    reid_available,
    update_gpu_memory,
)
from shared.core.config import CameraConfig
from shared.core.settings import get_settings
from shared.logging.logger import get_logger
from shared.types.events import DetectionPayload
from shared.types.models import FramePointer

log = get_logger(__name__)

DEFAULT_SKIP_N = 3
MIN_SKIP = 1
MAX_SKIP = 10
FAST_THRESHOLD = 0.020
SLOW_THRESHOLD = 0.050


class InferencePipeline:
    """Orchestrates inference stages with per-camera state isolation."""

    def __init__(self) -> None:
        self._cfg = get_settings()
        self._models = ModelManager()
        self._reid: ReIDService | None = None
        self._state_store = CameraStateStore(self._cfg)
        self._config_loader = InferenceConfigLoader(self._cfg)
        self._frame_input = FrameInput(self._cfg)
        self._telemetry = TelemetryPublisher()
        self._incidents = IncidentPublisher()

    async def load_models(self) -> None:
        self._reid = ReIDService(self._models.redis)
        reid_available.set(1 if self._reid.available else 0)
        await self._models.preload_all()
        log.info("Pipeline ready")

    def readiness_snapshot(self) -> dict[str, object]:
        return {
            "detector_loaded": self._models._detector is not None,
            "classifier_loaded": self._models._behavior_classifier is not None,
            "reid_available": bool(self._reid and self._reid.available),
        }

    def _new_state(self) -> CameraRuntimeState:
        return self._state_store.new_state()

    async def _load_camera_config(
        self,
        camera_id: str,
        redis: aioredis.Redis,
        state: CameraRuntimeState,
    ) -> CameraConfig:
        return await self._config_loader.load(camera_id, redis, state)

    async def process(self, payload: bytes | str, redis: aioredis.Redis) -> None:
        t0 = time.perf_counter()
        ptr: FramePointer | None = None
        try:
            ptr, frame = await self._frame_input.read(payload, redis)
        except Exception as exc:
            if "Stale frame pointer" in str(exc):
                await self._frame_input.cleanup_stale_pointer(ptr, redis)
            log.warning("Frame read failed", extra={"error": str(exc)})
            frames_dropped.inc()
            return

        state = self._state_store.get(ptr.camera_id)
        config = await self._config_loader.load(ptr.camera_id, redis, state)
        if not config.enabled:
            await self._telemetry.publish(redis, ptr, [], None, {})
            return

        detector = await self._models.get_detector()
        if state.frame_count % state.skip_n == 0:
            try:
                result = detector.detect_and_track(frame, tracker_id=ptr.camera_id)
                state.last_masks = result.person_masks
                state.last_items = [
                    det for det in result.items if float(det.get("conf", 0.0)) >= config.confidence_threshold
                ]
                state.last_tracks = [
                    {
                        "bbox": [float(v) for v in bbox],
                        "id": str(result.track_ids[i] if i < len(result.track_ids) else i + 1),
                        "label": "person",
                        "confidence": 1.0,
                    }
                    for i, bbox in enumerate(result.person_boxes)
                ]
            except Exception:
                detector_failures.inc()
                raise

        tracks = state.last_tracks or []
        item_detections = state.last_items or []
        state.frame_count += 1

        if self._reid and self._reid.available:
            await self._apply_reid(frame, tracks, config)

        state.interaction.update(tracks, item_detections)
        state.interaction.delete_stale_tracks()
        state.buffer.push(frame)

        detections = self._build_detections(tracks, item_detections)
        await self._maybe_classify(ptr, state, config, frame, detections, redis)

        telemetry_metadata = {
            "t_capture": ptr.t_capture,
            "t_output": time.time(),
            "config_version": int(config.loaded_at),
        }
        await self._telemetry.publish(redis, ptr, detections, state.current_incident, telemetry_metadata)

        elapsed = time.perf_counter() - t0
        inference_latency.observe(elapsed)
        frames_processed.inc()
        update_gpu_memory()
        self._adjust_skip_rate(state, elapsed)

    def _build_detections(
        self,
        tracks: list[dict],
        item_detections: list[dict],
    ) -> list[DetectionPayload]:
        detections = [
            DetectionPayload(
                bbox=track["bbox"],
                label="person",
                confidence=float(track.get("confidence", 1.0)),
                track_id=track["id"],
            )
            for track in tracks
        ]
        detections.extend(
            DetectionPayload(
                bbox=[float(v) for v in det["bbox"]],
                label=det["label"],
                confidence=float(det["conf"]),
            )
            for det in item_detections
        )
        return detections

    async def _maybe_classify(
        self,
        ptr: FramePointer,
        state: CameraRuntimeState,
        config: CameraConfig,
        frame: np.ndarray,
        detections: list[DetectionPayload],
        redis: aioredis.Redis,
    ) -> None:
        if not state.interaction.should_classify() or state.active_task:
            return
        clip = state.buffer.get_clip()
        state.active_task = True
        classifier = await self._models.get_behavior_classifier()
        classification_attempts.inc()
        task = asyncio.create_task(
            self._run_classification(ptr, clip, config, frame, detections, redis, classifier)
        )
        task.add_done_callback(lambda _task, cid=ptr.camera_id: self._state_store.mark_task_complete(cid))

    async def _apply_reid(self, frame: np.ndarray, tracks: list[dict], config: CameraConfig) -> None:
        if not self._reid or not self._reid.available:
            return
        for track in tracks:
            if str(track["id"]).startswith("global_"):
                continue
            try:
                bbox = [int(v) for v in track["bbox"]]
                x1, y1 = max(0, bbox[0]), max(0, bbox[1])
                x2, y2 = min(frame.shape[1], bbox[2]), min(frame.shape[0], bbox[3])
                if y2 <= y1 or x2 <= x1:
                    continue
                crop = frame[y1:y2, x1:x2]
                embedding = await asyncio.to_thread(self._reid.extract_features, crop)
                if embedding is None:
                    continue
                global_id = await self._reid.get_global_id(
                    embedding,
                    organization_id=config.organization_id,
                    store_id=config.store_id,
                )
                if global_id:
                    track["id"] = f"global_{global_id}"
                else:
                    await self._reid.register_track(
                        track["id"],
                        embedding,
                        organization_id=config.organization_id,
                        store_id=config.store_id,
                    )
                    track["id"] = f"global_{track['id']}"
            except Exception as exc:
                log.error("Re-ID failed", extra={"error": str(exc)})

    async def _run_classification(
        self,
        ptr: FramePointer,
        clip: list[np.ndarray],
        config: CameraConfig,
        frame: np.ndarray,
        detections: list[DetectionPayload],
        redis: aioredis.Redis,
        classifier: BehaviorClassifier,
    ) -> None:
        try:
            label, confidence = await asyncio.to_thread(classifier.classify_sync, clip)
            state = self._state_store.get(ptr.camera_id)
            if label == "normal" or confidence < self._cfg.alert_confidence_threshold:
                state.current_incident = None
                return
            evidence_uri, thumbnail_uri = await asyncio.to_thread(save_evidence_frame, frame, ptr.trace_id)
            state.current_incident = await self._incidents.publish(
                redis,
                ptr,
                label,
                confidence,
                detections,
                config,
                {"evidence_uri": evidence_uri, "thumbnail_uri": thumbnail_uri},
            )
            incidents_emitted.inc()
        except Exception as exc:
            classification_failures.inc()
            log.error("Classification failed", extra={"error": str(exc)})

    def _adjust_skip_rate(self, state: CameraRuntimeState, elapsed: float) -> None:
        if elapsed > SLOW_THRESHOLD:
            state.skip_n = min(state.skip_n + 1, MAX_SKIP)
        elif elapsed < FAST_THRESHOLD:
            state.skip_n = max(state.skip_n - 1, MIN_SKIP)
