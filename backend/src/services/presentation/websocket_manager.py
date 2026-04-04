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
        """Send one event to all subscribers matching the optional camera filter.

        BN-10: snapshot active connections under lock (fast), release lock, then
        fan out to all clients concurrently via asyncio.gather with a per-client
        timeout.  Stale connections are evicted in a final brief lock re-acquire
        so one slow client cannot block all others.
        """

        payload = message.model_dump(mode="json")

        # 1. Snapshot relevant connections (lock held only for dict read).
        async with self._lock:
            targets: list[WebSocket] = [
                ws
                for ws, subscribed_camera_id in self._connections.items()
                if not subscribed_camera_id or subscribed_camera_id == message.camera_id
            ]

        if not targets:
            return

        # 2. Send concurrently; collect failures without holding the lock.
        async def _send(ws: WebSocket) -> WebSocket | None:
            try:
                await asyncio.wait_for(ws.send_json(payload), timeout=2.0)
                self._metrics_recorder.record_websocket_message_sent(message.type)
                return None
            except Exception:  # pylint: disable=broad-except
                self._metrics_recorder.record_websocket_broadcast_failure(message.type)
                return ws

        results = await asyncio.gather(*(_send(ws) for ws in targets))
        stale_connections: list[WebSocket] = [ws for ws in results if ws is not None]

        if not stale_connections:
            return

        # 3. Evict stale connections under a brief re-lock.
        async with self._lock:
            for websocket in stale_connections:
                self._connections.pop(websocket, None)
        for _ in stale_connections:
            self._metrics_recorder.decrement_websocket_connections()
