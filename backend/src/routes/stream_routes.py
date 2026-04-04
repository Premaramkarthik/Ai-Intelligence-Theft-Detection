from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, WebSocket
from starlette.websockets import WebSocketDisconnect

from pydantic import BaseModel

from src.schemas.common import ApiResponse, WebSocketEnvelope
from src.schemas.stream_requests import StreamStartRequest, StreamStopRequest
from src.schemas.stream_responses import StreamInfoResponse
from src.utils.response import build_success_payload

router = APIRouter(prefix="/streams", tags=["Streams"])


class InferencePatchRequest(BaseModel):
    enabled: bool | None = None
    strategy: str | None = None  # "cnn_transformer" | "vjepa_probe"


def get_stream_service(request: Request):
    return request.app.state.container.stream_service


@router.post(
    "/{camera_id}/start",
    response_model=ApiResponse[StreamInfoResponse],
    summary="Start a stream worker",
)
async def start_stream(
    camera_id: str,
    request: Request,
    payload: StreamStartRequest | None = None,
) -> dict[str, Any]:
    stream_info = await get_stream_service(request).start_stream(
        camera_id,
        payload or StreamStartRequest(),
    )
    return build_success_payload(
        "Stream worker start request accepted.",
        stream_info.model_dump(mode="json"),
    )


@router.post(
    "/{camera_id}/stop",
    response_model=ApiResponse[StreamInfoResponse],
    summary="Stop a stream worker",
)
async def stop_stream(
    camera_id: str,
    request: Request,
    payload: StreamStopRequest | None = None,
) -> dict[str, Any]:
    stream_info = await get_stream_service(request).stop_stream(
        camera_id,
        payload or StreamStopRequest(),
    )
    return build_success_payload(
        "Stream worker stop request accepted.",
        stream_info.model_dump(mode="json"),
    )


@router.get(
    "/{camera_id}/status",
    response_model=ApiResponse[StreamInfoResponse],
    summary="Get stream status",
)
async def get_stream_status(camera_id: str, request: Request) -> dict[str, Any]:
    stream_info = await get_stream_service(request).get_stream_status(camera_id)
    return build_success_payload(
        "Stream status fetched successfully.",
        stream_info.model_dump(mode="json"),
    )


@router.get(
    "/{camera_id}/info",
    response_model=ApiResponse[StreamInfoResponse],
    summary="Get stream info contract",
)
async def get_stream_info(camera_id: str, request: Request) -> dict[str, Any]:
    stream_info = await get_stream_service(request).get_stream_info(camera_id)
    return build_success_payload(
        "Stream info fetched successfully.",
        stream_info.model_dump(mode="json"),
    )


@router.patch(
    "/{camera_id}/inference",
    response_model=ApiResponse[dict],
    summary="Configure inference for a stream",
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


@router.websocket("/ws/updates")
async def stream_updates(websocket: WebSocket) -> None:
    container = websocket.app.state.container
    camera_id = websocket.query_params.get("camera_id")
    await container.websocket_manager.connect(websocket, camera_id)
    try:
        snapshot = await container.stream_service.list_stream_contracts(camera_id)
        initial_message = WebSocketEnvelope(
            type="stream.snapshot",
            topic="stream.snapshot",
            message="Initial stream snapshot.",
            camera_id=camera_id,
            data={"items": [item.model_dump(mode="json") for item in snapshot]},
        )
        await websocket.send_json(initial_message.model_dump(mode="json"))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await container.websocket_manager.disconnect(websocket)
