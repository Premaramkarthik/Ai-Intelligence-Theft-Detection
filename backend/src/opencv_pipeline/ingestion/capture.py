"""Video ingestion built on top of OpenCV VideoCapture."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import cv2

from src.core.logger.logger import get_logger
from src.opencv_pipeline.buffering.frame_buffer import FrameBuffer
from src.opencv_pipeline.contracts import FramePacket, FrameSourceConfig, utc_now


@dataclass(slots=True)
class CaptureHealthSnapshot:
    """Health summary for one capture worker."""

    camera_id: str
    healthy: bool
    last_error: str | None
    sequence_number: int


class VideoCaptureWorker:
    """Capture frames from RTSP or local devices in a dedicated thread."""

    def __init__(
        self,
        source: FrameSourceConfig,
        frame_buffer: FrameBuffer,
        *,
        retry_initial_delay_seconds: float = 0.5,
        retry_max_delay_seconds: float = 5.0,
    ) -> None:
        self._source = source
        self._frame_buffer = frame_buffer
        self._retry_initial_delay_seconds = max(retry_initial_delay_seconds, 0.1)
        self._retry_max_delay_seconds = max(
            retry_max_delay_seconds,
            self._retry_initial_delay_seconds,
        )
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self._capture: cv2.VideoCapture | None = None
        self._logger = get_logger(__name__)
        self._sequence_number = 0
        self._last_error: str | None = None

    @property
    def camera_id(self) -> str:
        return self._source.camera_id

    def start(self) -> None:
        """Start the capture thread."""

        if self._thread is not None and self._thread.is_alive():
            return
        self._running.set()
        self._thread = threading.Thread(
            target=self._run,
            name=f"capture-{self._source.camera_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the capture thread and release the capture handle."""

        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def health_snapshot(self) -> CaptureHealthSnapshot:
        """Return a lightweight worker health snapshot."""

        return CaptureHealthSnapshot(
            camera_id=self._source.camera_id,
            healthy=self._last_error is None,
            last_error=self._last_error,
            sequence_number=self._sequence_number,
        )

    def _run(self) -> None:
        delay_seconds = self._retry_initial_delay_seconds
        while self._running.is_set():
            try:
                if self._capture is None or not self._capture.isOpened():
                    self._capture = self._open_capture()
                frame_grabbed, frame = self._capture.read()
                if not frame_grabbed or frame is None:
                    raise RuntimeError("blank frame grabbed")
                frame = self._normalize_frame(frame)
                self._last_error = None
                packet = FramePacket(
                    camera_id=self._source.camera_id,
                    stream_name=self._source.stream_name,
                    sequence_number=self._sequence_number,
                    captured_at=utc_now(),
                    monotonic_ns=time.perf_counter_ns(),
                    frame_bgr=frame,
                    width=frame.shape[1],
                    height=frame.shape[0],
                )
                self._sequence_number += 1
                self._frame_buffer.publish(packet)
                delay_seconds = self._retry_initial_delay_seconds
            except Exception as exc:  # pylint: disable=broad-except
                self._last_error = str(exc)
                self._logger.warning(
                    "Capture worker for %s failed: %s",
                    self._source.camera_id,
                    exc,
                )
                if self._capture is not None:
                    self._capture.release()
                    self._capture = None
                time.sleep(delay_seconds)
                delay_seconds = min(delay_seconds * 2.0, self._retry_max_delay_seconds)

    def _normalize_frame(self, frame) -> object:
        """Normalize capture output for downstream buffering and preprocessing."""

        target_width = int(self._source.target_width)
        target_height = int(self._source.target_height)
        if (
            target_width > 0
            and target_height > 0
            and (frame.shape[1] != target_width or frame.shape[0] != target_height)
        ):
            frame = cv2.resize(
                frame,
                (target_width, target_height),
                interpolation=cv2.INTER_LINEAR,
            )
        if not frame.flags.c_contiguous:
            frame = frame.copy()
        return frame

    def _open_capture(self) -> cv2.VideoCapture:
        capture = cv2.VideoCapture(
            self._source.source_uri,
            self._source.api_preference,
        )
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"unable to open source {self._source.source_uri!r}")

        if self._source.target_width > 0:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._source.target_width)
        if self._source.target_height > 0:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._source.target_height)
        if self._source.target_fps > 0:
            capture.set(cv2.CAP_PROP_FPS, self._source.target_fps)
        return capture
