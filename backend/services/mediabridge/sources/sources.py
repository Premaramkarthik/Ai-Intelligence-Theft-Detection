"""
Video input sources — RTSP / Webcam.
"""
from __future__ import annotations

import cv2
import numpy as np
import time
import subprocess
import os
from shared.logging.logger import get_logger

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
        self._cap = cv2.VideoCapture(src)
        if not self._cap.isOpened():
            log.error("Failed to open video source", extra={"src": src})

    def read(self) -> np.ndarray | None:
        ret, frame = self._cap.read()
        return frame if ret else None

    def release(self) -> None:
        if self._cap:
            self._cap.release()

    def is_opened(self) -> bool:
        return self._cap.isOpened()

class FFmpegSource(BaseSource):
    """Robust RTSP ingestion using a piped FFmpeg process."""
    def __init__(self, url: str) -> None:
        self._url = url
        # We assume 720p output for now, worker will resize if needed
        self._w, self._h = 1280, 720
        self._frame_size = self._w * self._h * 3
        self._proc: subprocess.Popen | None = None
        
        self._cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-hwaccel", "auto",
            "-i", url,
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{self._w}x{self._h}",
            "-an", "-sn",
            "-loglevel", "error",
            "pipe:1"
        ]
        
        try:
            self._proc = subprocess.Popen(
                self._cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                bufsize=self._frame_size
            )
            log.info("FFmpeg process started", extra={"url": url})
        except Exception as e:
            log.error("Failed to start FFmpeg", extra={"error": str(e)})
            self._proc = None

    def read(self) -> np.ndarray | None:
        if not self._proc:
            return None
        
        try:
            raw_frame = self._proc.stdout.read(self._frame_size)
            if len(raw_frame) != self._frame_size:
                return None
            
            frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((self._h, self._w, 3))
            return frame
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

    @staticmethod
    def construct_url(config: dict) -> list[str]:
        """Constructs RTSP URL(s) from config."""
        username = config.get("username")
        password = config.get("password")
        ip = config.get("ip_address")
        port = config.get("port", 554)
        substreams = config.get("substreams", [])
        
        if not all([username, password, ip]):
            raise ValueError("Incomplete RTSP configuration")
            
        urls = []
        for substream in substreams:
            url = f"rtsp://{username}:{password}@{ip}:{port}/{substream}"
            urls.append(url)
        return urls

def validate_source(src: str | int, timeout_s: float = 3.0) -> bool:
    """Check if source is actually readable using OpenCV (fast check)."""
    cap = cv2.VideoCapture(src)
    try:
        start = time.time()
        while time.time() - start < timeout_s:
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    return True
            time.sleep(0.1)
        return False
    except Exception as e:
        log.error("Validation error", extra={"error": str(e)})
        return False
    finally:
        cap.release()

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
