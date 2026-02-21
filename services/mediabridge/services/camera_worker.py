"""
CameraWorker — Per-camera capture + ROI crop + SHM write.
Moved from services.mediabridge.camera_worker
"""
from __future__ import annotations

import asyncio
import time

import cv2
import redis.asyncio as aioredis

from libs.shared.logging.logger import get_logger
from libs.shared.types.models import FramePointer
from libs.shared.core.settings import get_settings
from services.mediabridge.services.shm_writer import SHMWriter
from services.mediabridge.sources.sources import get_source
from services.mediabridge.utils.metrics import (
    frames_captured, frames_dropped, frame_latency, cameras_active,
)

log = get_logger(__name__)


class CameraWorker:
    def __init__(
        self,
        source_path: str,
        redis: aioredis.Redis,
        shutdown_event: asyncio.Event,
        camera_id: str,
    ) -> None:
        self._source_path = source_path
        self._camera_id = camera_id
        self._redis = redis
        self._shutdown_event = shutdown_event
        cfg = get_settings()
        self._h = cfg.frame_height
        self._w = cfg.frame_width
        self._shm = SHMWriter(
            camera_id,
            cfg.shm_slots_per_cam,
            self._h,
            self._w,
        )

    async def run(self) -> None:
        """Capture loop."""
        source = get_source(self._source_path)
        cameras_active.inc()
        log.info("Camera worker started", extra={"camera_id": self._camera_id, "source": self._source_path})
        
        try:
            while not self._shutdown_event.is_set():
                t_start = time.perf_counter()
                frame = source.read()
                if frame is None:
                    log.warning("Capture failed", extra={"camera_id": self._camera_id})
                    frames_dropped.labels(camera_id=self._camera_id).inc()
                    await asyncio.sleep(1)
                    continue

                # Resize if needed to match SHM buffer
                if frame.shape[0] != self._h or frame.shape[1] != self._w:
                    frame = cv2.resize(frame, (self._w, self._h))

                # Write to SHM
                slot_id = self._shm.write(frame)
                
                # Push metadata to Redis
                ptr = FramePointer(camera_id=self._camera_id, slot_id=slot_id, t_capture=time.time())
                await self._redis.rpush("frames", ptr.to_bytes())
                await self._redis.set(f"frame_ptr:{self._camera_id}", str(slot_id))

                latency = (time.perf_counter() - t_start) * 1000
                frame_latency.labels(camera_id=self._camera_id).set(latency)
                frames_captured.labels(camera_id=self._camera_id).inc()

                # Control FPS
                await asyncio.sleep(0.01) # Simple yield
        except Exception as e:
            log.exception("Camera worker encountered unhandled error", extra={"camera_id": self._camera_id, "error": str(e)})
        finally:
            source.release()
            self._shm.close()
            cameras_active.dec()
            log.info("Camera worker stopped", extra={"camera_id": self._camera_id})
