"""WebSocket connection registry and broadcast helper."""

from __future__ import annotations

import asyncio

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from src.observability.metrics import MetricsRecorder, NullMetricsRecorder
from src.schemas.common import WebSocketEnvelope


class WebSocketManager:
    """Track websocket subscriptions and broadcast backend events."""

    def __init__(self, metrics_recorder: MetricsRecorder | None = None) -> None:
        """Create a websocket registry optionally instrumented with metrics."""

        self._connections: dict[WebSocket, str | None] = {}
        self._lock = asyncio.Lock()
        self._metrics_recorder = metrics_recorder or NullMetricsRecorder()

    async def connect(self, websocket: WebSocket, camera_id: str | None) -> None:
        """Accept and register a websocket connection."""

        await websocket.accept()
        async with self._lock:
            self._connections[websocket] = camera_id
        self._metrics_recorder.increment_websocket_connections()

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a websocket connection when it closes or becomes stale."""

        removed = False
        async with self._lock:
            removed = self._connections.pop(websocket, None) is not None
        if removed:
            self._metrics_recorder.decrement_websocket_connections()

    async def broadcast(self, message: WebSocketEnvelope) -> None:
        """Send one event to all subscribers matching the optional camera filter."""

        stale_connections: list[WebSocket] = []
        payload = message.model_dump(mode="json")
        async with self._lock:
            for websocket, subscribed_camera_id in self._connections.items():
                if subscribed_camera_id and subscribed_camera_id != message.camera_id:
                    continue
                try:
                    await websocket.send_json(payload)
                    self._metrics_recorder.record_websocket_message_sent(message.type)
                except (RuntimeError, WebSocketDisconnect):
                    self._metrics_recorder.record_websocket_broadcast_failure(message.type)
                    stale_connections.append(websocket)
            for websocket in stale_connections:
                self._connections.pop(websocket, None)
        for _ in stale_connections:
            self._metrics_recorder.decrement_websocket_connections()
