from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status

from src.schemas.camera_requests import (
    CameraListQuery,
    CameraValidationRequest,
    CreateCameraRequest,
    UpdateCameraRequest,
)
from src.schemas.camera_responses import CameraResponse, CameraValidationResponse
from src.schemas.common import ApiResponse, PaginatedItems
from src.utils.response import build_success_payload

router = APIRouter(prefix="/cameras", tags=["Cameras"])


def get_camera_service(request: Request):
    return request.app.state.container.camera_service


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[CameraResponse],
    summary="Create a camera",
    description="Register a new RTSP camera and store its metadata.",
)
async def create_camera(
    payload: CreateCameraRequest,
    request: Request,
) -> dict[str, Any]:
    camera = await get_camera_service(request).create_camera(payload)
    return build_success_payload("Camera created successfully.", camera.model_dump(mode="json"))


@router.get(
    "",
    response_model=ApiResponse[PaginatedItems[CameraResponse]],
    summary="List cameras",
    description="List cameras with frontend-ready pagination and optional filtering.",
)
async def list_cameras(
    request: Request,
    query: Annotated[CameraListQuery, Depends()],
) -> dict[str, Any]:
    result = await get_camera_service(request).list_cameras(query)
    return build_success_payload("Cameras fetched successfully.", result.model_dump(mode="json"))


@router.get(
    "/{camera_id}",
    response_model=ApiResponse[CameraResponse],
    summary="Get camera details",
)
async def get_camera(camera_id: str, request: Request) -> dict[str, Any]:
    camera = await get_camera_service(request).get_camera(camera_id)
    return build_success_payload("Camera fetched successfully.", camera.model_dump(mode="json"))


@router.put(
    "/{camera_id}",
    response_model=ApiResponse[CameraResponse],
    summary="Update camera",
)
async def update_camera(
    camera_id: str,
    payload: UpdateCameraRequest,
    request: Request,
) -> dict[str, Any]:
    camera = await get_camera_service(request).update_camera(camera_id, payload)
    return build_success_payload("Camera updated successfully.", camera.model_dump(mode="json"))


@router.delete(
    "/{camera_id}",
    response_model=ApiResponse[dict[str, str]],
    summary="Delete camera",
)
async def delete_camera(camera_id: str, request: Request) -> dict[str, Any]:
    await get_camera_service(request).delete_camera(camera_id)
    inference_manager = getattr(request.app.state.container, "inference_manager", None)
    if inference_manager is not None:
        await inference_manager.remove_camera(camera_id)
    return build_success_payload("Camera deleted successfully.", {"id": camera_id})


@router.post(
    "/{camera_id}/validate",
    response_model=ApiResponse[CameraValidationResponse],
    summary="Validate RTSP connectivity",
    description="Validate the camera RTSP endpoint and return machine-readable status information.",
)
async def validate_camera(
    camera_id: str,
    request: Request,
    payload: CameraValidationRequest | None = None,
) -> dict[str, Any]:
    validation = await get_camera_service(request).validate_camera(
        camera_id,
        timeout_seconds=payload.timeout_seconds if payload else None,
    )
    return build_success_payload("Camera validation completed.", validation.model_dump(mode="json"))
