"""Realtime websocket and inference-control routes."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request, WebSocket
from pydantic import BaseModel, model_validator
from starlette.websockets import WebSocketDisconnect

from src.schemas.common import ApiResponse, WebSocketEnvelope
from src.utils.response import build_success_payload

router = APIRouter(prefix="/streams", tags=["Streams"])


class InferencePatchRequest(BaseModel):
    """Patch payload for enabling or reconfiguring inference on a camera."""

    enabled: bool | None = None
    strategy: Literal["vjepa_probe", "cnn_transformer"] | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "InferencePatchRequest":
        if self.enabled is None and self.strategy is None:
            raise ValueError("At least one of enabled or strategy must be provided.")
        return self


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
    container = request.app.state.container
    await container.camera_service.get_camera_record(camera_id)
    stream_record = await container.stream_control_service.configure_inference(
        camera_id,
        enabled=payload.enabled,
        strategy=payload.strategy,
    )
    inference_metadata = stream_record.metadata.get("inference")
    if not isinstance(inference_metadata, dict):
        inference_metadata = {}
    return build_success_payload(
        "Inference configuration updated.",
        {
            "camera_id": camera_id,
            "enabled": inference_metadata.get("enabled"),
            "strategy": inference_metadata.get("strategy"),
            "worker_refresh_interval_seconds": (
                container.settings.opencv_pipeline_inference_control_refresh_interval_seconds
            ),
        },
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
