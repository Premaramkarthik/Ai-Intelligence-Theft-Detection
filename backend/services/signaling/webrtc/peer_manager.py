from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import uuid4

from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
import redis.asyncio as aioredis

from services.signaling.utils.metrics import (
    webrtc_active_peers,
    webrtc_ice_failures,
    webrtc_negotiation_failures,
    webrtc_viewers_per_camera,
)
from services.signaling.webrtc.schemas import IceServerConfig
from services.signaling.webrtc.tracks import CameraVideoTrack
from shared.core.settings import get_settings
from shared.logging.logger import get_logger

log = get_logger(__name__)


@dataclass
class ManagedPeer:
    session_id: str
    camera_id: str
    connection: RTCPeerConnection
    state: str = "connecting"


class WebRTCPeerManager:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._peers: dict[str, ManagedPeer] = {}
        self._lock = asyncio.Lock()

    def ice_servers(self) -> list[IceServerConfig]:
        servers: list[IceServerConfig] = []
        stun_urls = [url.strip() for url in self._settings.webrtc_stun_urls.split(",") if url.strip()]
        if stun_urls:
            servers.append(IceServerConfig(urls=stun_urls))
        if self._settings.webrtc_turn_url:
            servers.append(
                IceServerConfig(
                    urls=[self._settings.webrtc_turn_url],
                    username=self._settings.webrtc_turn_username or None,
                    credential=self._settings.webrtc_turn_password or None,
                )
            )
        return servers

    def _rtc_ice_servers(self) -> list[RTCIceServer]:
        servers: list[RTCIceServer] = []
        for server in self.ice_servers():
            servers.append(
                RTCIceServer(
                    urls=server.urls,
                    username=server.username,
                    credential=server.credential,
                )
            )
        return servers

    def viewers_for_camera(self, camera_id: str) -> int:
        return sum(1 for peer in self._peers.values() if peer.camera_id == camera_id)

    def get_peer(self, session_id: str) -> ManagedPeer | None:
        return self._peers.get(session_id)

    async def _wait_for_ice_gathering(self, pc: RTCPeerConnection) -> None:
        if pc.iceGatheringState == "complete":
            return

        loop = asyncio.get_running_loop()
        finished = loop.create_future()

        @pc.on("icegatheringstatechange")
        async def _on_ice_gathering_state_change() -> None:
            if pc.iceGatheringState == "complete" and not finished.done():
                finished.set_result(None)

        try:
            await asyncio.wait_for(finished, timeout=self._settings.webrtc_gather_timeout_s)
        except asyncio.TimeoutError:
            log.warning(
                "Timed out waiting for WebRTC ICE gathering",
                extra={"state": pc.iceGatheringState, "timeout_s": self._settings.webrtc_gather_timeout_s},
            )

    async def create_answer(self, redis: aioredis.Redis, camera_id: str, offer_sdp: str, offer_type: str) -> ManagedPeer:
        async with self._lock:
            if self.viewers_for_camera(camera_id) >= self._settings.max_preview_viewers_per_camera:
                raise RuntimeError("Camera viewer limit reached")

            pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=self._rtc_ice_servers()))
            session_id = uuid4().hex
            peer = ManagedPeer(session_id=session_id, camera_id=camera_id, connection=pc)
            self._peers[session_id] = peer
            webrtc_active_peers.inc()
            webrtc_viewers_per_camera.labels(camera_id=camera_id).set(self.viewers_for_camera(camera_id))

        @pc.on("connectionstatechange")
        async def _on_connectionstatechange() -> None:
            peer.state = pc.connectionState
            if pc.connectionState in {"failed", "closed", "disconnected"}:
                webrtc_ice_failures.labels(camera_id=camera_id).inc()
                await self.close_peer(session_id)

        try:
            pc.addTrack(CameraVideoTrack(redis, camera_id))
            await pc.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type=offer_type))
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await self._wait_for_ice_gathering(pc)
            peer.state = "connected"
            return peer
        except Exception:
            webrtc_negotiation_failures.labels(camera_id=camera_id).inc()
            await self.close_peer(session_id)
            raise

    async def close_peer(self, session_id: str) -> None:
        async with self._lock:
            peer = self._peers.pop(session_id, None)
        if peer is None:
            return
        try:
            await peer.connection.close()
        finally:
            webrtc_active_peers.dec()
            webrtc_viewers_per_camera.labels(camera_id=peer.camera_id).set(self.viewers_for_camera(peer.camera_id))

    async def close_all(self) -> None:
        async with self._lock:
            session_ids = list(self._peers.keys())
        for session_id in session_ids:
            await self.close_peer(session_id)


peer_manager = WebRTCPeerManager()
