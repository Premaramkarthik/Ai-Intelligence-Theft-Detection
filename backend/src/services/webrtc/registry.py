"""Registry that maps camera_id → active WebRTC video tracks.

Each connected browser client gets its own CameraVideoStreamTrack. The registry
fans the latest annotated frame out to every live track on each push_frame() call.

Thread/async safety notes
--------------------------
* push_frame() is called from the asyncio pipeline loop; it never acquires a lock
  and always iterates a *snapshot* of the track list so concurrent remove_track()
  cannot cause a RuntimeError mid-iteration.
* create_track() / remove_track() use an asyncio.Lock for mutation safety.
* The last-frame cache (_last_frames) is written only by push_frame() (single
  asyncio task) so it is safe to read without a lock from create_track().
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

import numpy as np

from src.services.webrtc.video_track import CameraVideoStreamTrack

_log = logging.getLogger(__name__)


class WebRTCRegistry:
    """Thread-safe fan-out registry: camera_id → [CameraVideoStreamTrack, ...]."""

    def __init__(self) -> None:
        self._tracks: dict[str, list[CameraVideoStreamTrack]] = defaultdict(list)
        # Caches the most recent annotated frame per camera so newly created
        # tracks can be seeded immediately — eliminates the startup stall where
        # recv() would block until the pipeline delivers the first frame.
        self._last_frames: dict[str, np.ndarray] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Track lifecycle
    # ------------------------------------------------------------------

    async def create_track(self, camera_id: str) -> CameraVideoStreamTrack:
        """Allocate a new track for one viewer, pre-seeded with the last known frame."""
        track = CameraVideoStreamTrack()

        # Seed the track before registering it so recv() has a frame ready
        # the moment aiortc's RTP sender calls it.
        last = self._last_frames.get(camera_id)
        if last is not None:
            track.seed_frame(last)
            _log.debug("registry: seeded new track for camera %s with cached frame", camera_id)
        else:
            _log.debug(
                "registry: no cached frame for camera %s — track will use black fallback", camera_id
            )

        async with self._lock:
            self._tracks[camera_id].append(track)

        _log.info(
            "registry: track created camera=%s active_viewers=%d",
            camera_id,
            len(self._tracks[camera_id]),
        )
        return track

    async def remove_track(self, camera_id: str, track: CameraVideoStreamTrack) -> None:
        """Deregister a track when its peer connection closes."""
        async with self._lock:
            try:
                self._tracks[camera_id].remove(track)
            except ValueError:
                pass
        _log.info(
            "registry: track removed camera=%s remaining_viewers=%d",
            camera_id,
            len(self._tracks.get(camera_id, [])),
        )

    # ------------------------------------------------------------------
    # Pipeline side
    # ------------------------------------------------------------------

    def push_frame(self, camera_id: str, frame_bgr: np.ndarray) -> None:
        """Fan the latest annotated frame out to all active viewers of camera_id.

        Always non-blocking. Iterates a snapshot so concurrent remove_track()
        cannot corrupt the iteration.
        """
        # Cache before fan-out so create_track() always gets the freshest frame.
        self._last_frames[camera_id] = frame_bgr

        snapshot = list(self._tracks.get(camera_id, []))
        for track in snapshot:
            track.push_frame(frame_bgr)

        if snapshot:
            _log.debug("registry: pushed frame camera=%s viewers=%d", camera_id, len(snapshot))

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def active_track_count(self, camera_id: str) -> int:
        return len(self._tracks.get(camera_id, []))

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Drop all track references (called on app shutdown after PCs are closed)."""
        self._tracks.clear()
        self._last_frames.clear()
