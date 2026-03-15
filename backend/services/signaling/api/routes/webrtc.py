from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status

from services.signaling.api.deps import get_redis, verify_jwt
from services.signaling.webrtc.peer_manager import peer_manager
from services.signaling.webrtc.schemas import (
    WebRTCAnswerResponse,
    WebRTCConfigResponse,
    WebRTCOfferRequest,
    WebRTCSessionInfo,
)
from shared.core.settings import get_settings

router = APIRouter()


@router.get("/camera/{camera_id}/webrtc/config", response_model=WebRTCConfigResponse)
async def get_webrtc_config(
    camera_id: str,
    _user: str = Depends(verify_jwt),
) -> WebRTCConfigResponse:
    settings = get_settings()
    if not settings.webrtc_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="WebRTC preview is disabled")
    return WebRTCConfigResponse(ice_servers=peer_manager.ice_servers())


@router.post("/camera/{camera_id}/webrtc/offer", response_model=WebRTCAnswerResponse)
async def create_webrtc_offer(
    camera_id: str,
    request: WebRTCOfferRequest,
    _user: str = Depends(verify_jwt),
    redis: aioredis.Redis = Depends(get_redis),
) -> WebRTCAnswerResponse:
    settings = get_settings()
    if not settings.webrtc_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="WebRTC preview is disabled")

    try:
        peer = await peer_manager.create_answer(redis, camera_id, request.sdp, request.type)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"WebRTC negotiation failed: {exc}") from exc

    local = peer.connection.localDescription
    if local is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Missing local WebRTC description")

    return WebRTCAnswerResponse(
        session_id=peer.session_id,
        sdp=local.sdp,
        type=local.type,
        ice_servers=peer_manager.ice_servers(),
    )


@router.get("/camera/{camera_id}/webrtc/session/{session_id}", response_model=WebRTCSessionInfo)
async def get_webrtc_session(
    camera_id: str,
    session_id: str,
    _user: str = Depends(verify_jwt),
) -> WebRTCSessionInfo:
    peer = peer_manager.get_peer(session_id)
    if peer is None or peer.camera_id != camera_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WebRTC session not found")
    return WebRTCSessionInfo(session_id=session_id, camera_id=camera_id, state=peer.state)


@router.delete("/camera/{camera_id}/webrtc/session/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webrtc_session(
    camera_id: str,
    session_id: str,
    _user: str = Depends(verify_jwt),
) -> None:
    peer = peer_manager.get_peer(session_id)
    if peer is not None and peer.camera_id != camera_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WebRTC session not found")
    await peer_manager.close_peer(session_id)
