"""
CameraWorker — Per-camera capture + SHM write with auto-reconnection.
"""
from __future__ import annotations

import asyncio
import time
import uuid

import cv2
import redis.asyncio as aioredis

from shared.logging.logger import get_logger
from shared.types.models import FramePointer
from shared.core.settings import get_settings
from services.mediabridge.services.shm_writer import SHMWriter
from services.mediabridge.sources.sources import get_source, BaseSource
from services.mediabridge.utils.metrics import (
    frames_captured, frames_dropped, frame_latency, cameras_active,
)

log = get_logger(__name__)

MAX_CONSECUTIVE_FAILURES = 10
BACKOFF_CAP_S = 30.0


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

    async def _set_status(self, status: str) -> None:
        await self._redis.set(f"camera_status:{self._camera_id}", status)

    async def _reconnect(self) -> BaseSource | None:
        """Reconnect with exponential backoff."""
        delay = 1.0
        while not self._shutdown_event.is_set():
            log.warning("Reconnecting", extra={"camera_id": self._camera_id, "delay": delay})
            await self._set_status("reconnecting")

            source = get_source(self._source_path)
            if source.is_opened():
                log.info("Reconnected", extra={"camera_id": self._camera_id})
                await self._set_status("online")
                return source

            source.release()
            await asyncio.sleep(min(delay, BACKOFF_CAP_S))
            delay *= 2
        return None

    async def run(self) -> None:
        """Capture loop with auto-reconnection."""
        source = get_source(self._source_path)
        if not source.is_opened():
            log.error("Initial connection failed", extra={"camera_id": self._camera_id})
            source = await self._reconnect()
            if source is None:
                return

        cameras_active.inc()
        await self._set_status("online")
        log.info("Camera worker started", extra={"camera_id": self._camera_id, "source": self._source_path})

        consecutive_failures = 0
        try:
            while not self._shutdown_event.is_set():
                t_start = time.perf_counter()
                frame = source.read()

                if frame is None:
                    consecutive_failures += 1
                    frames_dropped.labels(camera_id=self._camera_id).inc()

                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        log.warning(
                            "Too many capture failures, reconnecting",
                            extra={"camera_id": self._camera_id, "failures": consecutive_failures},
                        )
                        source.release()
                        source = await self._reconnect()
                        if source is None:
                            break
                        consecutive_failures = 0
                    else:
                        await asyncio.sleep(0.1)
                    continue

                consecutive_failures = 0

                if frame.shape[0] != self._h or frame.shape[1] != self._w:
                    frame = cv2.resize(frame, (self._w, self._h))

                trace_id = str(uuid.uuid4())[:8]
                slot_id = self._shm.write(frame)

                ptr = FramePointer(
                    camera_id=self._camera_id,
                    slot_id=slot_id,
                    t_capture=time.time(),
                    trace_id=trace_id,
                )
                await self._redis.rpush("frames", ptr.to_bytes())
                await self._redis.set(f"frame_ptr:{self._camera_id}", str(slot_id))

                latency = (time.perf_counter() - t_start) * 1000
                frame_latency.labels(camera_id=self._camera_id).set(latency)
                frames_captured.labels(camera_id=self._camera_id).inc()

                await asyncio.sleep(0.01)
        except Exception as e:
            log.exception("Camera worker crashed", extra={"camera_id": self._camera_id, "error": str(e)})
        finally:
            source.release()
            self._shm.close()
            cameras_active.dec()
            await self._set_status("offline")
            log.info("Camera worker stopped", extra={"camera_id": self._camera_id})
