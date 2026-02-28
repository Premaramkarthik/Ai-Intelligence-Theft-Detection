"""
PersonTracker — ByteTrack wrapper.
Moved from services.inference.tracking.person_tracker
"""
from __future__ import annotations

import numpy as np
from shared.logging.logger import get_logger

log = get_logger(__name__)


class PersonTracker:
    def __init__(self) -> None:
        # In a real scenario, this would initialize ByteTrack
        self._tracks: dict[int, dict] = {}
        log.info("PersonTracker initialized")

    def update(self, bboxes: list[list[float]]) -> list[dict]:
        """
        Update tracks with new detections.
        For now, a simple mock that returns track info.
        """
        # Simple mock tracking logic
        updated_tracks = []
        for i, bbox in enumerate(bboxes):
            track_id = i + 1  # Mock ID
            self._tracks[track_id] = {"bbox": bbox, "id": track_id}
            updated_tracks.append(self._tracks[track_id])
        
        return updated_tracks
