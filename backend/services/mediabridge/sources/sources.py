"""
Video input sources — RTSP / Webcam / WebRTC.
Moved from services.mediabridge.video_input.sources
"""
from __future__ import annotations

import cv2
import numpy as np

from shared.logging.logger import get_logger

log = get_logger(__name__)

class BaseSource:
    def read(self) -> np.ndarray | None:
        raise NotImplementedError
    def release(self) -> None:
        pass

class OpenCVSource(BaseSource):
    def __init__(self, src: str) -> None:
        # If numeric, convert to int (webcam index)
        try:
            actual_src = int(src)
            log.info("Initializing Webcam source", extra={"device_id": actual_src})
        except (ValueError, TypeError):
            actual_src = src
            log.info("Initializing RTSP source", extra={"url": src})
            
        self._cap = cv2.VideoCapture(actual_src)
        if not self._cap.isOpened():
            log.error("Failed to open video source", extra={"src": src})

    def read(self) -> np.ndarray | None:
        ret, frame = self._cap.read()
        return frame if ret else None

    def release(self) -> None:
        self._cap.release()

def get_source(src: str) -> BaseSource:
    return OpenCVSource(src)
