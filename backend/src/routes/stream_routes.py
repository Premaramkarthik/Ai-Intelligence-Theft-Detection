"""Realtime websocket and inference-control routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, WebSocket
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect

from src.schemas.common import ApiResponse, WebSocketEnvelope
from src.utils.response import build_success_payload

router = APIRouter(prefix="/streams", tags=["Streams"])


class InferencePatchRequest(BaseModel):
    """Patch payload for enabling or reconfiguring inference on a camera."""

    enabled: bool | None = None
    strategy: str | None = None


@router.patch(
    "/{camera_id}/inference",
    response_model=ApiResponse[dict[str, Any]],
    summary="Configure inference for a camera stream",
)
async def patch_inference(
    camera_id: str,
    request: Request,
    payload: InferencePatchRequest,
) -> dict[str, Any]:
    inference_manager = request.app.state.container.inference_manager
    await inference_manager.configure_stream(
        camera_id,
        enabled=payload.enabled,
        strategy=payload.strategy,
    )
    return build_success_payload(
        "Inference configuration updated.",
        {"camera_id": camera_id, "enabled": payload.enabled, "strategy": payload.strategy},
    )


@router.get(
    "/health",
    response_model=ApiResponse[dict[str, Any]],
    summary="Get realtime event bridge health",
)
async def stream_health(request: Request) -> dict[str, Any]:
    consumer = getattr(request.app.state.container, "stream_event_consumer", None)
    snapshot = consumer.health_snapshot() if consumer is not None else {"healthy": True}
    return build_success_payload("Stream consumer health fetched successfully.", snapshot)


@router.websocket("/ws/updates")
async def stream_updates(websocket: WebSocket) -> None:
    """Fan out Kafka-backed realtime events to browser websocket clients."""

    container = websocket.app.state.container
    camera_id = websocket.query_params.get("camera_id")
    await container.websocket_manager.connect(websocket, camera_id)
    try:
        initial_message = WebSocketEnvelope(
            type="stream.bootstrap",
            topic="stream.bootstrap",
            message="Realtime event websocket connected.",
            camera_id=camera_id,
            data={
                "camera_id": camera_id,
                "kafka_consumer": (
                    container.stream_event_consumer.health_snapshot()
                    if getattr(container, "stream_event_consumer", None) is not None
                    else {"healthy": True}
                ),
            },
        )
        await websocket.send_json(initial_message.model_dump(mode="json"))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await container.websocket_manager.disconnect(websocket)
