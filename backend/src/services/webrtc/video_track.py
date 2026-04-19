"""Per-client WebRTC video track fed by the OpenCV pipeline.

Frame delivery model
--------------------
WebRTC (aiortc) is PULL-based: the RTP sender task calls recv() at a fixed
rate (~30 fps).  The OpenCV pipeline is PUSH-based: frames arrive at ~10 fps.

The correct model for this mismatch is "latest-frame":

    push_frame()  →  store frame in self._latest_frame   (O(1), no lock)
    recv()        →  next_timestamp() paces the clock     (~33 ms sleep)
                  →  read self._latest_frame and return   (immediate, no wait)

When the pipeline is slower than 30 fps, recv() returns the same frame
multiple times.  H.264 encodes those as near-zero-cost P-frames (no change),
so bandwidth impact is negligible and the browser decoder never stalls.

Why a Queue is wrong here
--------------------------
A queue requires recv() to *wait* for the producer.  But aiortc's RTP sender
is a single asyncio task calling recv() in a tight loop — if recv() blocks
beyond next_timestamp()'s sleep, the sender stall propagates directly to the
browser as frozen or black video.  Using asyncio.wait_for() on a queue simply
trades an indefinite block for a bounded one; the root mismatch remains.
The latest-frame model eliminates the wait entirely.

Async safety
------------
Both push_frame() and recv() execute in the same single-threaded asyncio event
loop.  Attribute assignment in CPython is atomic (GIL), so no lock is needed.
"""

from __future__ import annotations

import logging

import av
import numpy as np
from aiortc import VideoStreamTrack

_log = logging.getLogger(__name__)

# Shared black fallback returned before the first pipeline frame arrives.
# 720p matches the pipeline's default resolution; shape only affects the
# fallback — once push_frame() is called the real dimensions are used.
_BLACK_FRAME: np.ndarray = np.zeros((720, 1280, 3), dtype=np.uint8)


class CameraVideoStreamTrack(VideoStreamTrack):
    """One WebRTC video track for a single viewer of one camera.

    Public interface used by the registry
    -------------------------------------
    push_frame(frame_bgr)  – called by the pipeline on every annotated frame
    seed_frame(frame_bgr)  – called once by the registry on track creation
    """

    kind = "video"

    def __init__(self) -> None:
        super().__init__()
        # Latest annotated frame from the pipeline.  Written by push_frame()
        # (pipeline side) and read by recv() (aiortc sender side).
        # None only until the first push_frame() / seed_frame() call.
        self._latest_frame: np.ndarray | None = None

    # ------------------------------------------------------------------
    # Pipeline side — called from OutputDispatcher, must stay non-blocking
    # ------------------------------------------------------------------

    def push_frame(self, frame_bgr: np.ndarray) -> None:
        """Store the latest annotated frame.  O(1), no lock, no copy."""
        self._latest_frame = frame_bgr

    def seed_frame(self, frame_bgr: np.ndarray) -> None:
        """Pre-load the last known frame so recv() never returns black on startup."""
        self._latest_frame = frame_bgr

    # ------------------------------------------------------------------
    # WebRTC sender side — called by aiortc's RTP sender task at ~30 fps
    # ------------------------------------------------------------------

    async def recv(self) -> av.VideoFrame:
        """Return the latest available frame to the RTP sender.

        Contract:
        - Returns in ≤ next_timestamp() sleep time (~33 ms at 30 fps).
        - Never blocks waiting for a pipeline frame.
        - Always produces a valid av.VideoFrame with monotonically increasing PTS.
        - When the pipeline is slow, the same frame is repeated; H.264 encodes
          these as near-zero-cost P-frames so bandwidth stays minimal.
        """
        # next_timestamp() sleeps until it is time for the next RTP packet
        # (based on the negotiated clock rate).  This is the ONLY await in
        # recv() — no queue, no timeout, no second wait.
        pts, time_base = await self.next_timestamp()

        frame_bgr = self._latest_frame
        if frame_bgr is None:
            frame_bgr = _BLACK_FRAME
            _log.debug("recv pts=%d: no pipeline frame yet — returning black fallback", pts)
        else:
            _log.debug("recv pts=%d: returning latest frame shape=%s", pts, frame_bgr.shape)

        av_frame = av.VideoFrame.from_ndarray(frame_bgr, format="bgr24")
        av_frame = av_frame.reformat(format="yuv420p")
        av_frame.pts = pts
        av_frame.time_base = time_base
        return av_frame
