"""
CameraWorker — Per-camera capture + SHM write with auto-reconnection.
"""
from __future__ import annotations

import asyncio
import time

import cv2
import redis.asyncio as aioredis

from shared.logging.logger import get_logger
from shared.redis import camera_status_key, enqueue_frame, frame_pointer_key
from shared.tracing import new_trace_id
from shared.types.models import FramePointer
from shared.core.settings import get_settings
from services.mediabridge.services.shm_writer import SHMWriter
from services.mediabridge.sources.sources import get_source, BaseSource
from services.mediabridge.utils.metrics import (
    camera_state_transitions,
    cameras_active,
    frame_latency,
    frames_captured,
    frames_dropped,
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
        self._frame_queue_maxlen = cfg.frame_queue_maxlen
        self._frame_interval_s = 1.0 / max(cfg.camera_stream_fps, 0.1)
        self._shm = SHMWriter(
            camera_id,
            cfg.shm_slots_per_cam,
            self._h,
            self._w,
        )

    async def _set_status(self, status: str) -> None:
        await self._redis.set(camera_status_key(self._camera_id), status)
        camera_state_transitions.labels(camera_id=self._camera_id, state=status).inc()

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
        await self._redis.delete(frame_pointer_key(self._camera_id))
        source = get_source(self._source_path)
        if not source.is_opened():
            log.error("Initial connection failed", extra={"camera_id": self._camera_id})
            source = await self._reconnect()
            if source is None:
                return

        cameras_active.inc()
        await self._set_status("online")
        log.info(
            "Camera worker started",
            extra={
                "camera_id": self._camera_id,
                "source": self._source_path,
                "target_fps": round(1.0 / self._frame_interval_s, 2),
            },
        )

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
                        await self._redis.delete(frame_pointer_key(self._camera_id))
                        source = await self._reconnect()
                        if source is None:
                            break
                        consecutive_failures = 0
                    else:
                        await asyncio.sleep(0.1)
                    continue

                consecutive_failures = 0

                if frame.ndim == 2:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                elif frame.ndim == 3 and frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                if frame.shape[0] != self._h or frame.shape[1] != self._w:
                    frame = cv2.resize(frame, (self._w, self._h))

                trace_id = new_trace_id()
                slot_id, generation = self._shm.write(frame)

                ptr = FramePointer(
                    camera_id=self._camera_id,
                    slot_id=slot_id,
                    generation=generation,
                    t_capture=time.time(),
                    trace_id=trace_id,
                )
                payload = ptr.to_bytes().decode("utf-8")
                await enqueue_frame(
                    self._redis,
                    self._camera_id,
                    payload,
                    self._frame_queue_maxlen,
                )
                await self._redis.set(frame_pointer_key(self._camera_id), payload)

                latency = (time.perf_counter() - t_start) * 1000
                frame_latency.labels(camera_id=self._camera_id).set(latency)
                frames_captured.labels(camera_id=self._camera_id).inc()

                elapsed_s = time.perf_counter() - t_start
                sleep_s = max(0.0, self._frame_interval_s - elapsed_s)
                if sleep_s:
                    await asyncio.sleep(sleep_s)
        except Exception as e:
            log.exception("Camera worker crashed", extra={"camera_id": self._camera_id, "error": str(e)})
        finally:
            source.release()
            self._shm.close()
            cameras_active.dec()
            await self._set_status("offline")
            log.info("Camera worker stopped", extra={"camera_id": self._camera_id})
