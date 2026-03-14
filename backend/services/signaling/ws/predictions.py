"""WS /ws/predictions - authenticated telemetry stream."""
from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from services.signaling.api.deps import verify_ws_token
from shared.logging.logger import get_logger

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
    redis: aioredis.Redis = websocket.app.state.redis
    pubsub = redis.pubsub()
    await pubsub.psubscribe("telemetry:*", "incidents:*")
    try:
        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                data = message["data"]
                await websocket.send_text(data.decode("utf-8") if isinstance(data, bytes) else data)
    except WebSocketDisconnect:
        log.info("Predictions WS client disconnected")
    finally:
        await pubsub.punsubscribe("telemetry:*", "incidents:*")
        await pubsub.aclose()
