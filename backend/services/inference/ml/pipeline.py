"""
InferencePipeline orchestrates detection, temporal analysis, and event emission.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

import numpy as np
import redis.asyncio as aioredis

from services.inference.ml.engines.shoplifting_model import ShopliftingModel
from services.inference.ml.model_manager import ModelManager
from services.inference.services.interaction import ItemInteractionDetector
from services.inference.services.reid_service import ReIDService
from services.inference.services.temporal_buffer import TemporalBuffer
from services.inference.utils.metrics import (
    frames_dropped,
    frames_processed,
    inference_latency,
    update_gpu_memory,
)
from shared.core.settings import get_settings
from shared.logging.logger import get_logger
from shared.types.events import (
    DetectionPayload,
    FrameReference,
    FrameTelemetryMessage,
    IncidentEvent,
    IncidentPayload,
    Severity,
    utc_now_iso,
)
from shared.types.models import FramePointer

log = get_logger(__name__)

DEFAULT_SKIP_N = 3
MIN_SKIP = 1
MAX_SKIP = 10
FAST_THRESHOLD = 0.020
SLOW_THRESHOLD = 0.050
INCIDENT_STREAM = "stream:incidents"
STREAM_MAXLEN = 10000


@dataclass
class CameraConfig:
    enabled: bool = True
    confidence_threshold: float = 0.45
    hand_dist_px: int = 80
    loaded_at: float = 0.0


@dataclass
class CameraRuntimeState:
    interaction: ItemInteractionDetector
    buffer: TemporalBuffer
    frame_count: int = 0
    skip_n: int = DEFAULT_SKIP_N
    last_masks: list | None = None
    last_items: list | None = None
    last_tracks: list[dict] | None = None
    active_task: bool = False
    current_incident: IncidentPayload | None = None
    config: CameraConfig | None = None


class InferencePipeline:
    """Orchestrates inference stages with per-camera state isolation."""

    def __init__(self) -> None:
        self._cfg = get_settings()
        self._models = ModelManager()
        self._reid: ReIDService | None = None
        self._camera_states: dict[str, CameraRuntimeState] = {}

    async def load_models(self) -> None:
        self._reid = ReIDService(self._models.redis)
        await self._models.preload_all()
        log.info("Pipeline ready")

    def _new_state(self) -> CameraRuntimeState:
        return CameraRuntimeState(
            interaction=ItemInteractionDetector(
                hand_dist_px=self._cfg.hand_dist_px,
                interaction_frames=self._cfg.interaction_frames,
            ),
            buffer=TemporalBuffer(maxlen=self._cfg.temporal_window),
            last_masks=[],
            last_items=[],
            last_tracks=[],
        )

    async def _load_camera_config(self, camera_id: str, redis: aioredis.Redis, state: CameraRuntimeState) -> CameraConfig:
        now = time.time()
        if state.config and now - state.config.loaded_at < self._cfg.config_poll_interval_s:
            return state.config

        raw = await redis.hgetall(f"config:{camera_id}")
        config = CameraConfig(
            enabled=raw.get("enabled", "true") == "true",
            confidence_threshold=float(raw.get("confidence_threshold", self._cfg.default_confidence_threshold)),
            hand_dist_px=int(raw.get("hand_dist_px", self._cfg.hand_dist_px)),
            loaded_at=now,
        )
        state.interaction = ItemInteractionDetector(
            hand_dist_px=config.hand_dist_px,
            interaction_frames=self._cfg.interaction_frames,
        )
        state.config = config
        return config

    async def process(self, payload: bytes | str, redis: aioredis.Redis) -> None:
        t0 = time.perf_counter()
        try:
            payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload
            ptr = FramePointer.from_bytes(payload_bytes)
            from shared.shm.ring_buffer import ReaderCache

            reader = ReaderCache.get_reader(
                ptr.camera_id,
                self._cfg.shm_slots_per_cam,
                self._cfg.frame_height,
                self._cfg.frame_width,
            )
            frame = reader.read(ptr.slot_id, expected_generation=ptr.generation)
        except Exception as exc:
            log.warning("Frame read failed", extra={"error": str(exc)})
            frames_dropped.inc()
            return

        state = self._camera_states.setdefault(ptr.camera_id, self._new_state())
        config = await self._load_camera_config(ptr.camera_id, redis, state)
        if not config.enabled:
            await self._publish_telemetry(redis, ptr, [], None, {})
            return

        detector = await self._models.get_detector()
        if not detector:
            return

        if state.frame_count % state.skip_n == 0:
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

        tracks = state.last_tracks or []
        item_detections = state.last_items or []
        state.frame_count += 1

        if self._reid:
            await self._apply_reid(frame, tracks)

        state.interaction.update(tracks, item_detections)
        state.interaction.delete_stale_tracks()
        state.buffer.push(frame)

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

        classifier = await self._models.get_shoplifting_model()
        if classifier and state.interaction.should_classify() and not state.active_task:
            clip = state.buffer.get_clip()
            state.active_task = True
            task = asyncio.create_task(self._run_classification(ptr, clip, detections, redis, classifier))
            task.add_done_callback(lambda _task, cid=ptr.camera_id: self._mark_task_complete(cid))

        telemetry_metadata = {
            "t_capture": ptr.t_capture,
            "t_output": time.time(),
            "config_version": int(config.loaded_at),
        }
        await self._publish_telemetry(redis, ptr, detections, state.current_incident, telemetry_metadata)

        elapsed = time.perf_counter() - t0
        inference_latency.observe(elapsed)
        frames_processed.inc()
        update_gpu_memory()

        if elapsed > SLOW_THRESHOLD:
            state.skip_n = min(state.skip_n + 1, MAX_SKIP)
        elif elapsed < FAST_THRESHOLD:
            state.skip_n = max(state.skip_n - 1, MIN_SKIP)

    async def _apply_reid(self, frame: np.ndarray, tracks: list[dict]) -> None:
        if not self._reid:
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
                global_id = await self._reid.get_global_id(embedding)
                if global_id:
                    track["id"] = f"global_{global_id}"
                else:
                    await self._reid.register_track(track["id"], embedding)
                    track["id"] = f"global_{track['id']}"
            except Exception as exc:
                log.error("Re-ID failed", extra={"error": str(exc)})

    def _mark_task_complete(self, camera_id: str) -> None:
        state = self._camera_states.get(camera_id)
        if state:
            state.active_task = False

    async def _publish_telemetry(
        self,
        redis: aioredis.Redis,
        ptr: FramePointer,
        detections: list[DetectionPayload],
        incident: IncidentPayload | None,
        metadata: dict,
    ) -> None:
        telemetry = FrameTelemetryMessage(
            camera_id=ptr.camera_id,
            trace_id=ptr.trace_id,
            timestamp=utc_now_iso(),
            capture_timestamp=ptr.t_capture,
            detections=detections,
            incident=incident,
            frame_ref=FrameReference(
                camera_id=ptr.camera_id,
                slot_id=ptr.slot_id,
                generation=ptr.generation,
            ),
            metadata=metadata,
        )
        payload = telemetry.model_dump_json()
        await redis.publish(f"telemetry:{ptr.camera_id}", payload)
        await redis.set(f"telemetry:latest:{ptr.camera_id}", payload)

    async def _run_classification(
        self,
        ptr: FramePointer,
        clip: list[np.ndarray],
        detections: list[DetectionPayload],
        redis: aioredis.Redis,
        classifier: ShopliftingModel,
    ) -> None:
        try:
            label, confidence = await classifier.classify(clip)
            state = self._camera_states[ptr.camera_id]
            if label == "normal" or confidence < self._cfg.alert_confidence_threshold:
                state.current_incident = None
                return

            incident = IncidentPayload(
                label=label,
                confidence=float(confidence),
                severity=Severity.HIGH if confidence < 0.95 else Severity.CRITICAL,
            )
            state.current_incident = incident
            event = IncidentEvent(
                camera_id=ptr.camera_id,
                trace_id=ptr.trace_id,
                timestamp=utc_now_iso(),
                label=label,
                confidence=float(confidence),
                severity=incident.severity,
                detections=detections,
                frame_ref=FrameReference(
                    camera_id=ptr.camera_id,
                    slot_id=ptr.slot_id,
                    generation=ptr.generation,
                ),
                metadata={
                    "t_capture": ptr.t_capture,
                    "t_output": time.time(),
                    "model": self._cfg.model_name,
                },
            )
            payload = event.model_dump_json()
            await redis.xadd(INCIDENT_STREAM, {"payload": payload}, maxlen=STREAM_MAXLEN)
            await redis.publish(f"incidents:{ptr.camera_id}", payload)
        except Exception as exc:
            log.error("Classification failed", extra={"error": str(exc)})
