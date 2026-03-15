"""
Spatial interaction detector for person-item proximity over time.
"""
from __future__ import annotations

import math
import time

from shared.logging.logger import get_logger

log = get_logger(__name__)

TRACK_TIMEOUT_S = 30.0
LOWER_BODY_Y_FRACTION = 0.65
LOWER_BODY_HEIGHT_FRACTION = 0.35
OVERLAP_TRIGGER_RATIO = 0.05


class ItemInteractionDetector:
    def __init__(self, hand_dist_px: int = 80, interaction_frames: int = 5) -> None:
        self._hand_dist_px = hand_dist_px
        self._interaction_frames = interaction_frames
        self._states: dict[str | int, int] = {}
        self._tracks: dict[str | int, float] = {}
        self._should_classify = False
        log.info(
            "ItemInteractionDetector initialized",
            extra={"dist": hand_dist_px, "frames": interaction_frames},
        )

    @property
    def hand_dist_px(self) -> int:
        return self._hand_dist_px

    @property
    def interaction_frames(self) -> int:
        return self._interaction_frames

    def configure(self, hand_dist_px: int, interaction_frames: int) -> bool:
        changed = (
            self._hand_dist_px != hand_dist_px
            or self._interaction_frames != interaction_frames
        )
        if not changed:
            return False
        self._hand_dist_px = hand_dist_px
        self._interaction_frames = interaction_frames
        log.info(
            "ItemInteractionDetector reconfigured",
            extra={"dist": hand_dist_px, "frames": interaction_frames},
        )
        return True

    def _lower_body_zone(self, bbox: list[float]) -> tuple[float, float, float, float]:
        x1, y1, x2, y2 = bbox
        body_height = max(0.0, y2 - y1)
        zone_top = y1 + body_height * LOWER_BODY_Y_FRACTION
        return x1, zone_top, x2, y2

    def _bbox_center(self, bbox: list[float]) -> tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def _overlap_ratio(self, a: tuple[float, float, float, float], b: list[float]) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
        inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
        inter_area = inter_w * inter_h
        item_area = max(1.0, (bx2 - bx1) * (by2 - by1))
        return inter_area / item_area

    def _is_interacting(self, track: dict, detection: dict) -> bool:
        person_bbox = [float(v) for v in track["bbox"]]
        item_bbox = [float(v) for v in detection["bbox"]]
        lower_zone = self._lower_body_zone(person_bbox)
        overlap_ratio = self._overlap_ratio(lower_zone, item_bbox)
        if overlap_ratio >= OVERLAP_TRIGGER_RATIO:
            return True

        zone_center = self._bbox_center(list(lower_zone))
        item_center = self._bbox_center(item_bbox)
        distance = math.dist(zone_center, item_center)
        return distance <= float(self._hand_dist_px)

    def update(self, tracks: list[dict], detections: list[dict]) -> None:
        self._should_classify = False
        now = time.perf_counter()
        seen_track_ids: set[str | int] = set()

        for track in tracks:
            tid = track["id"]
            seen_track_ids.add(tid)
            self._tracks[tid] = now
            interacting = any(self._is_interacting(track, detection) for detection in detections)
            if interacting:
                self._states[tid] = self._states.get(tid, 0) + 1
                if self._states[tid] >= self._interaction_frames:
                    self._should_classify = True
                    self._states[tid] = 0
                    log.info("Interaction trigger", extra={"track_id": tid})
            else:
                self._states[tid] = 0

        for tid in list(self._states):
            if tid not in seen_track_ids and tid not in self._tracks:
                del self._states[tid]

    def delete_stale_tracks(self) -> None:
        now = time.perf_counter()
        stale_ids = [
            tid
            for tid, last_seen in self._tracks.items()
            if now - last_seen > TRACK_TIMEOUT_S
        ]
        for tid in stale_ids:
            del self._tracks[tid]
            self._states.pop(tid, None)
            log.debug("Track timed out", extra={"track_id": tid})

    def should_classify(self) -> bool:
        return self._should_classify
