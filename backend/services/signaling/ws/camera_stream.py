"""WS /ws/camera/{camera_id} - authenticated live camera stream."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from services.signaling.api.deps import verify_ws_token
from services.signaling.services.camera_service import build_stream_message, grab_jpeg, grab_metadata
from shared.core.settings import get_settings
from shared.logging.logger import get_logger

router = APIRouter()
log = get_logger(__name__)


@router.websocket("/ws/camera/{camera_id}")
async def ws_camera(websocket: WebSocket, camera_id: str) -> None:
    try:
        verify_ws_token(websocket)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    settings = get_settings()
    interval = 1.0 / settings.camera_stream_fps
    try:
        while True:
            jpeg, metadata = await asyncio.gather(
                grab_jpeg(websocket.app.state.redis, camera_id),
                grab_metadata(camera_id, websocket.app.state.redis),
            )
            if jpeg is not None:
                await websocket.send_text(json.dumps(build_stream_message(camera_id, jpeg, metadata)))
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        log.info("Camera WS disconnected", extra={"camera_id": camera_id})
    except Exception as exc:
        log.error("Camera WS error", extra={"camera_id": camera_id, "error": str(exc)})
