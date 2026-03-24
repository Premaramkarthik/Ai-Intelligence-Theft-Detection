from __future__ import annotations

import asyncio

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from src.schemas.common import WebSocketEnvelope


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, str | None] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, camera_id: str | None) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[websocket] = camera_id

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(websocket, None)

    async def broadcast(self, message: WebSocketEnvelope) -> None:
        stale_connections: list[WebSocket] = []
        payload = message.model_dump(mode="json")
        async with self._lock:
            for websocket, subscribed_camera_id in self._connections.items():
                if subscribed_camera_id and subscribed_camera_id != message.camera_id:
                    continue
                try:
                    await websocket.send_json(payload)
                except (RuntimeError, WebSocketDisconnect):
                    stale_connections.append(websocket)
            for websocket in stale_connections:
                self._connections.pop(websocket, None)
