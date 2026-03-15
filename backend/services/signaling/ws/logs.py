"""WS /ws/logs — streams Redis logs to browser clients."""
from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from services.signaling.api.deps import verify_ws_token
from services.signaling.utils.metrics import websocket_clients
from shared.logging.logger import get_logger

router = APIRouter()
log = get_logger(__name__)

LOGS_CHANNEL = "logs"

@router.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket) -> None:
    try:
        verify_ws_token(websocket)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    websocket_clients.labels(channel="logs").inc()
    redis: aioredis.Redis = websocket.app.state.redis
    pubsub = redis.pubsub()
    await pubsub.subscribe(LOGS_CHANNEL)
    log.info("Logs WS client connected")
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        log.info("Logs WS client disconnected")
    finally:
        websocket_clients.labels(channel="logs").dec()
        await pubsub.unsubscribe(LOGS_CHANNEL)
        await pubsub.aclose()
