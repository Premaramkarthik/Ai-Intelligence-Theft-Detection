"""
Video input sources — RTSP / Webcam.
"""
from __future__ import annotations

import cv2
import numpy as np
import os
import shutil
import subprocess
import threading
from shared.logging.logger import get_logger
from shared.validation import validate_source

log = get_logger(__name__)

class BaseSource:
    def read(self) -> np.ndarray | None:
        raise NotImplementedError
    def release(self) -> None:
        pass
    def is_opened(self) -> bool:
        raise NotImplementedError

class OpenCVSource(BaseSource):
    def __init__(self, src: str | int) -> None:
        self._src = src
        # Force V4L2 for webcam indices on Linux to avoid FFmpeg warnings and improve stability
        if isinstance(src, int):
            self._cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
        else:
            self._cap = cv2.VideoCapture(src)
            
        if not self._cap.isOpened():
            log.error("Failed to open video source", extra={"src": src})

    def read(self) -> np.ndarray | None:
        ret, frame = self._cap.read()
        if not ret or frame is None:
            return None
        if frame.ndim == 2:
            return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        if frame.ndim == 3 and frame.shape[2] == 4:
            return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        return frame

    def release(self) -> None:
        if self._cap:
            self._cap.release()

    def is_opened(self) -> bool:
        return self._cap.isOpened()

def _has_nvdec() -> bool:
    """Check if NVDEC hardware decode is available."""
    return shutil.which("nvidia-smi") is not None


class FFmpegSource(BaseSource):
    """Robust RTSP ingestion using a piped FFmpeg process."""
    def __init__(self, url: str) -> None:
        self._url = url
        self._w, self._h = 1280, 720
        self._frame_size = self._w * self._h * 3
        self._proc: subprocess.Popen | None = None
        self._stderr_thread: threading.Thread | None = None

        cmd = ["ffmpeg"]
        if _has_nvdec():
            cmd.extend(["-hwaccel", "cuda"])
            log.info("FFmpeg using NVDEC GPU decode")
        else:
            cmd.extend(["-hwaccel", "auto"])

        cmd.extend([
            "-rtsp_transport", "tcp",
            "-i", url,
            "-vf", f"scale={self._w}:{self._h},format=bgr24",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-an", "-sn",
            "-loglevel", "error",
            "pipe:1",
        ])

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=self._frame_size,
            )
            # Drain stderr in background to prevent pipe deadlock
            self._stderr_thread = threading.Thread(
                target=self._drain_stderr, daemon=True
            )
            self._stderr_thread.start()
            log.info("FFmpeg process started", extra={"url": url})
        except Exception as e:
            log.error("Failed to start FFmpeg", extra={"error": str(e)})
            self._proc = None

    def _drain_stderr(self) -> None:
        """Read stderr continuously to prevent pipe buffer deadlock."""
        if self._proc and self._proc.stderr:
            for line in self._proc.stderr:
                log.debug("FFmpeg stderr", extra={"line": line.decode(errors="replace").strip()})

    def read(self) -> np.ndarray | None:
        if not self._proc or not self._proc.stdout:
            return None
        try:
            raw_frame = self._proc.stdout.read(self._frame_size)
            if len(raw_frame) != self._frame_size:
                return None
            return np.frombuffer(raw_frame, dtype=np.uint8).reshape(
                (self._h, self._w, 3)
            )
        except Exception:
            return None

    def release(self) -> None:
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            log.info("FFmpeg process terminated")

    def is_opened(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

class WebcamSource(OpenCVSource):
    def __init__(self, device_index: int = 0) -> None:
        super().__init__(device_index)
        log.info("Initialized Webcam source", extra={"device_index": device_index})

class RTSPSource(FFmpegSource):
    def __init__(self, url: str) -> None:
        super().__init__(url)
        log.info("Initialized RTSP source (FFmpeg)", extra={"url": url})

def get_source(src: str | int) -> BaseSource:
    # If it's a numeric string, cast to int (webcam index)
    if isinstance(src, str) and src.isdigit():
        return WebcamSource(int(src))
    if isinstance(src, int):
        return WebcamSource(src)
    
    # Priority to FFmpeg for RTSP/URLs
    if isinstance(src, str) and (src.startswith("rtsp://") or src.startswith("http")):
        return FFmpegSource(src)
        
    return OpenCVSource(src)
