"""WS /ws/camera/{camera_id} — MJPEG stream of live camera frames over WebSocket."""
from __future__ import annotations

import asyncio

import cv2
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from libs.shared.logging.logger import get_logger
from libs.shared.core.settings import get_settings
from services.signaling.services.camera_service import grab_jpeg

router = APIRouter()
log = get_logger(__name__)


@router.websocket("/ws/camera/{camera_id}")
async def ws_camera(websocket: WebSocket, camera_id: str) -> None:
    await websocket.accept()
    settings = get_settings()
    interval = 1.0 / settings.camera_stream_fps
    log.info("Camera WS connected", extra={"camera_id": camera_id})
    try:
        while True:
            jpeg = await grab_jpeg(websocket.app.state.redis, camera_id)
            if jpeg is not None:
                await websocket.send_bytes(jpeg)
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        log.info("Camera WS disconnected", extra={"camera_id": camera_id})
    except Exception as exc:
        log.error("Camera WS error", extra={"camera_id": camera_id, "error": str(exc)})
