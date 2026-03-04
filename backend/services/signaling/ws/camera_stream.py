"""WS /ws/camera/{camera_id} — live camera stream with backpressure."""
from __future__ import annotations

import asyncio
import json

import cv2
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.logging.logger import get_logger
from shared.core.settings import get_settings
from services.signaling.services.camera_service import grab_jpeg, grab_metadata

router = APIRouter()
log = get_logger(__name__)

WS_SEND_TIMEOUT = 0.1  # Drop frame if send takes >100ms


@router.websocket("/ws/camera/{camera_id}")
async def ws_camera(websocket: WebSocket, camera_id: str) -> None:
    await websocket.accept()
    settings = get_settings()
    interval = 1.0 / settings.camera_stream_fps
    log.info("Camera WS connected", extra={"camera_id": camera_id})
    try:
        while True:
            jpeg, metadata = await asyncio.gather(
                grab_jpeg(websocket.app.state.redis, camera_id),
                grab_metadata(camera_id, websocket.app.state.redis),
            )

            if jpeg is not None:
                # Binary frame + text metadata (avoids base64 overhead)
                try:
                    await asyncio.wait_for(
                        websocket.send_bytes(jpeg), timeout=WS_SEND_TIMEOUT
                    )
                    await websocket.send_text(json.dumps({
                        "detections": metadata.get("detections", []),
                        "action": metadata.get("action"),
                    }))
                except asyncio.TimeoutError:
                    pass  # Drop frame — slow client backpressure

            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        log.info("Camera WS disconnected", extra={"camera_id": camera_id})
    except Exception as exc:
        log.error("Camera WS error", extra={"camera_id": camera_id, "error": str(exc)})
