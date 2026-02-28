"""WS /ws/logs — streams Redis logs to browser clients."""
from __future__ import annotations

import asyncio
import json

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.logging.logger import get_logger

router = APIRouter()
log = get_logger(__name__)

LOGS_CHANNEL = "logs"

@router.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket) -> None:
    await websocket.accept()
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
        await pubsub.unsubscribe(LOGS_CHANNEL)
        await pubsub.aclose()
