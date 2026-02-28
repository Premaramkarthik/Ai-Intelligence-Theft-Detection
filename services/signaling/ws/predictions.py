"""WS /ws/predictions — streams Redis inference events to browser clients."""
from __future__ import annotations

import asyncio
import json

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.logging.logger import get_logger
from services.signaling.api.deps import get_redis

router = APIRouter()
log = get_logger(__name__)

PREDICTIONS_CHANNEL = "predictions"


@router.websocket("/ws/predictions")
async def ws_predictions(websocket: WebSocket) -> None:
    await websocket.accept()
    redis: aioredis.Redis = websocket.app.state.redis
    pubsub = redis.pubsub()
    # Subscribe to all detections:* channels
    await pubsub.psubscribe("detections:*")
    log.info("Predictions WS client connected (pattern detections:*)")
    try:
        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                await websocket.send_text(message["data"].decode("utf-8") if isinstance(message["data"], bytes) else message["data"])
    except WebSocketDisconnect:
        log.info("Predictions WS client disconnected")
    finally:
        await pubsub.punsubscribe("detections:*")
        await pubsub.aclose()
