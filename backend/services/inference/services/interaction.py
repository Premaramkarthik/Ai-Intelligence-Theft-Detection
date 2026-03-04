"""
ItemInteractionDetector — proximity + temporal gate state machine.
Moved from services.inference.interaction.item_interaction
"""
from __future__ import annotations

import time
from shared.logging.logger import get_logger

log = get_logger(__name__)

TRACK_TIMEOUT_S = 30.0

class ItemInteractionDetector:
    def __init__(self, hand_dist_px: int = 80, interaction_frames: int = 5) -> None:
        self._hand_dist_px = hand_dist_px
        self._interaction_frames = interaction_frames
        self._states: dict[str | int, int] = {}  # track_id -> frame_count
        self._tracks: dict[str | int, float] = {} # track_id -> last_seen
        self._should_classify = False
        log.info("ItemInteractionDetector initialized", extra={"dist": hand_dist_px, "frames": interaction_frames})

    def update(self, tracks: list[dict], detections: list) -> None:
        """Update interaction state machine based on person tracks and item detections."""
        self._should_classify = False
        now = time.perf_counter()
        
        for track in tracks:
            tid = track["id"]
            self._tracks[tid] = now
            # Mock logic: if we detected an item near hands, increment state
            # In real code, we'd check distance between hands and items
            self._states[tid] = self._states.get(tid, 0) + 1
            if self._states[tid] >= self._interaction_frames:
                self._should_classify = True
                self._states[tid] = 0 # Reset after trigger
                log.info("Interaction trigger", extra={"track_id": tid})

    def delete_stale_tracks(self) -> None:
        """Remove tracks that have been inactive for too long."""
        now = time.perf_counter()
        stale_ids = [
            tid
            for tid, last_seen in self._tracks.items()
            if now - last_seen > TRACK_TIMEOUT_S
        ]
        for tid in stale_ids:
            del self._tracks[tid]
            if tid in self._states:
                del self._states[tid]
            log.debug("Track timed out", extra={"track_id": tid})

    def should_classify(self) -> bool:
        return self._should_classify
