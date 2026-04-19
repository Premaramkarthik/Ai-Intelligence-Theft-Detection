"""WebRTC SDP signaling endpoint with proper PC lifecycle management."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription

from src.services.webrtc.registry import WebRTCRegistry
from src.services.webrtc.video_track import CameraVideoStreamTrack

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/webrtc", tags=["WebRTC"])

_RTC_CONFIG = RTCConfiguration(
    iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])]
)

# Global store — keeps every RTCPeerConnection strongly referenced until it is
# explicitly closed.  Without this, Python GC can destroy a PC whose background
# RTP-sender tasks are still running, causing "Task was destroyed but pending!".
_active_pcs: set[RTCPeerConnection] = set()

_ICE_GATHER_TIMEOUT_S = 10.0


class SdpOffer(BaseModel):
    sdp: str
    type: str


class SdpAnswer(BaseModel):
    sdp: str
    type: str


async def _cleanup(
    pc: RTCPeerConnection,
    camera_id: str,
    track: CameraVideoStreamTrack,
    registry: WebRTCRegistry,
) -> None:
    """Ordered teardown: stop track → remove from registry → close PC → remove from global set.

    Calling track.stop() before pc.close() lets aiortc's RTP sender task exit
    cleanly via CancelledError rather than being destroyed mid-await.
    """
    _active_pcs.discard(pc)
    track.stop()
    await registry.remove_track(camera_id, track)
    if pc.connectionState != "closed":
        try:
            await pc.close()
        except Exception as exc:  # pylint: disable=broad-except
            _log.debug("PC close error (benign during shutdown): %s", exc)
    _log.info("webrtc: peer connection closed camera=%s state=%s", camera_id, pc.connectionState)


async def close_all_peer_connections() -> None:
    """Close every active PC on application shutdown — call from lifespan finally."""
    pcs = list(_active_pcs)
    _log.info("webrtc: closing %d active peer connection(s) on shutdown", len(pcs))
    await asyncio.gather(*(pc.close() for pc in pcs), return_exceptions=True)
    _active_pcs.clear()


@router.post(
    "/offer/{camera_id}",
    response_model=SdpAnswer,
    summary="Exchange WebRTC SDP offer for a camera stream",
)
async def create_webrtc_offer(
    camera_id: str,
    offer: SdpOffer,
    request: Request,
) -> SdpAnswer:
    container = request.app.state.container
    registry: WebRTCRegistry = container.webrtc_registry

    active_ids = {c.id for c in await container.camera_service.list_active_camera_records()}
    if camera_id not in active_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera {camera_id!r} is not active.",
        )

    track = await registry.create_track(camera_id)
    pc = RTCPeerConnection(configuration=_RTC_CONFIG)
    _active_pcs.add(pc)
    pc.addTrack(track)

    # --- ICE gathering event so we can wait below ---
    gather_done = asyncio.Event()

    @pc.on("icegatheringstatechange")
    def _on_ice_gather() -> None:
        _log.debug("webrtc: ICE gathering state=%s camera=%s", pc.iceGatheringState, camera_id)
        if pc.iceGatheringState == "complete":
            gather_done.set()

    # --- Connection state cleanup ---
    @pc.on("connectionstatechange")
    async def _on_conn_state() -> None:
        _log.info(
            "webrtc: connection state=%s camera=%s", pc.connectionState, camera_id
        )
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await _cleanup(pc, camera_id, track, registry)

    # --- SDP exchange ---
    await pc.setRemoteDescription(RTCSessionDescription(sdp=offer.sdp, type=offer.type))
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # Wait for the server's ICE gathering to complete before returning the SDP.
    # Without this wait the answer may contain no usable candidates and the
    # browser will fail to reach the STUN-reflexive address.
    if pc.iceGatheringState != "complete":
        try:
            await asyncio.wait_for(gather_done.wait(), timeout=_ICE_GATHER_TIMEOUT_S)
        except asyncio.TimeoutError:
            _log.warning(
                "webrtc: ICE gathering timed out after %.1fs camera=%s — returning partial SDP",
                _ICE_GATHER_TIMEOUT_S,
                camera_id,
            )

    _log.info(
        "webrtc: SDP answer ready camera=%s candidates_gathered=%s",
        camera_id,
        pc.iceGatheringState,
    )
    return SdpAnswer(sdp=pc.localDescription.sdp, type=pc.localDescription.type)
