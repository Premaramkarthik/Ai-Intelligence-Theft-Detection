"""WS /ws/predictions - authenticated telemetry stream."""
from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from services.signaling.api.deps import verify_ws_token
from services.signaling.utils.metrics import websocket_clients
from shared.logging.logger import get_logger
from shared.redis.keys import INCIDENT_CHANNEL_PATTERN, TELEMETRY_CHANNEL_PATTERN

router = APIRouter()
log = get_logger(__name__)


@router.websocket("/ws/predictions")
async def ws_predictions(websocket: WebSocket) -> None:
    try:
        verify_ws_token(websocket)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    websocket_clients.labels(channel="predictions").inc()
    redis: aioredis.Redis = websocket.app.state.redis
    pubsub = redis.pubsub()
    await pubsub.psubscribe(TELEMETRY_CHANNEL_PATTERN, INCIDENT_CHANNEL_PATTERN)
    try:
        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                data = message["data"]
                await websocket.send_text(data.decode("utf-8") if isinstance(data, bytes) else data)
    except WebSocketDisconnect:
        log.info("Predictions WS client disconnected")
    finally:
        websocket_clients.labels(channel="predictions").dec()
        await pubsub.punsubscribe(TELEMETRY_CHANNEL_PATTERN, INCIDENT_CHANNEL_PATTERN)
        await pubsub.aclose()
