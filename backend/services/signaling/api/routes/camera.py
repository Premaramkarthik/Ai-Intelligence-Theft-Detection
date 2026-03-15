"""GET /api/camera/{camera_id}/snapshot — returns JPEG frame."""
from __future__ import annotations

import hashlib

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse

from services.signaling.api.deps import get_redis, verify_jwt
from services.signaling.services.camera_service import grab_jpeg, mjpeg_stream
from services.signaling.schemas.camera import CameraConnectRequest, ConnectResponse
from shared.core.config import CameraConfig, camera_config_mapping
from shared.redis.keys import CAMERA_SOURCES_KEY, camera_config_key
from shared.validation import validate_source

router = APIRouter()


@router.get(
    "/camera/{camera_id}/snapshot",
    response_class=Response,
)
async def snapshot(
    camera_id: str,
    _user: str = Depends(verify_jwt),
    redis: aioredis.Redis = Depends(get_redis),
) -> Response:
    jpeg = await grab_jpeg(redis, camera_id)
    if jpeg is None:
        raise HTTPException(status_code=503, detail="No frame available")
    return Response(content=jpeg, media_type="image/jpeg")


@router.get("/camera/{camera_id}/mjpeg")
async def camera_mjpeg(
    camera_id: str,
    _user: str = Depends(verify_jwt),
    redis: aioredis.Redis = Depends(get_redis),
) -> StreamingResponse:
    return StreamingResponse(
        mjpeg_stream(redis, camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.post(
    "/camera/connect",
    response_model=ConnectResponse,
)
async def connect_camera(
    request: CameraConnectRequest,
    _user: str = Depends(verify_jwt),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Connects to a new camera source.
    Validates connection before adding to Redis.
    """
    sources_to_add = {}
    
    if request.source_type == "webcam":
        device_index = 0
        if not validate_source(device_index):
            raise HTTPException(status_code=400, detail=f"Webcam {device_index} not available")
        
        cam_id = f"webcam_{device_index}"
        existing = await redis.hget(CAMERA_SOURCES_KEY, cam_id)
        if existing == str(device_index):
            return ConnectResponse(
                status="success",
                message="Camera already connected",
                stream_ids=[cam_id],
                organization_id=request.organization_id,
                store_id=request.store_id,
            )
        sources_to_add[cam_id] = str(device_index)
        
    elif request.source_type == "rtsp":
        if not request.rtsp_config:
            raise HTTPException(status_code=400, detail="RTSP config missing")

        rtsp_url = request.rtsp_config.rtsp_url.strip()
        if not rtsp_url:
            raise HTTPException(status_code=400, detail="RTSP URL is required")
        if not validate_source(rtsp_url):
            raise HTTPException(status_code=400, detail="RTSP stream failed to connect")

        stream_hash = hashlib.sha1(rtsp_url.encode("utf-8")).hexdigest()[:12]
        cam_id = f"rtsp_{stream_hash}"
        existing = await redis.hget(CAMERA_SOURCES_KEY, cam_id)
        if existing == rtsp_url:
            return ConnectResponse(
                status="success",
                message="Camera already connected",
                stream_ids=[cam_id],
                organization_id=request.organization_id,
                store_id=request.store_id,
            )
        sources_to_add[cam_id] = rtsp_url
    else:
        raise HTTPException(status_code=400, detail="Invalid source_type")

    for cam_id, src in sources_to_add.items():
        await redis.hset(CAMERA_SOURCES_KEY, cam_id, src)
        # Also seed default config if not exists
        config_key = camera_config_key(cam_id)
        if not await redis.exists(config_key):
             await redis.hset(
                config_key,
                mapping=camera_config_mapping(
                    CameraConfig(
                        camera_id=cam_id,
                        organization_id=request.organization_id,
                        store_id=request.store_id,
                        confidence_threshold=0.5,
                        iou_threshold=0.15,
                        hand_dist_px=80,
                        enabled=True,
                    )
                ),
            )
            
    return ConnectResponse(
        status="success",
        message=f"Connected {len(sources_to_add)} stream(s)",
        stream_ids=list(sources_to_add.keys()),
        organization_id=request.organization_id,
        store_id=request.store_id,
    )
