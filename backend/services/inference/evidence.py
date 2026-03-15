from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from shared.core.settings import get_settings


def save_evidence_frame(frame: np.ndarray, trace_id: str) -> tuple[str | None, str | None]:
    settings = get_settings()
    evidence_dir = Path(settings.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    frame_path = evidence_dir / f"{trace_id}.jpg"
    thumb_path = evidence_dir / f"{trace_id}.thumb.jpg"

    if not cv2.imwrite(str(frame_path), frame):
        return None, None

    thumbnail = cv2.resize(frame, (320, 180))
    if not cv2.imwrite(str(thumb_path), thumbnail):
        thumb_path = frame_path

    return str(frame_path), str(thumb_path)
