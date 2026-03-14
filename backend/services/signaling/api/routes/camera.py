"""GET /api/camera/{camera_id}/snapshot — returns JPEG frame."""
from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from services.signaling.api.deps import get_redis, verify_jwt
from services.signaling.services.camera_service import grab_jpeg
from services.signaling.schemas.camera import CameraConnectRequest, ConnectResponse
from services.mediabridge.sources.sources import validate_source, RTSPSource

router = APIRouter()
CAMERA_SOURCES_KEY = "camera_sources"


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
        device_index = request.device_index if request.device_index is not None else 0
        if not validate_source(device_index):
            raise HTTPException(status_code=400, detail=f"Webcam {device_index} not available")
        
        cam_id = f"webcam_{device_index}"
        existing = await redis.hget(CAMERA_SOURCES_KEY, cam_id)
        if existing == str(device_index):
            return ConnectResponse(
                status="success",
                message="Camera already connected",
                stream_ids=[cam_id],
            )
        sources_to_add[cam_id] = str(device_index)
        
    elif request.source_type == "rtsp":
        if not request.rtsp_config:
            raise HTTPException(status_code=400, detail="RTSP config missing")
        
        try:
            urls = RTSPSource.construct_url(request.rtsp_config.model_dump())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
            
        if not urls:
             raise HTTPException(status_code=400, detail="No substreams provided")
             
        for i, url in enumerate(urls):
            if not validate_source(url):
                 # Should we fail all or just this one? 
                 # Requirement says "Attempt connection immediately"
                 raise HTTPException(status_code=400, detail=f"RTSP stream {i} matching substream {request.rtsp_config.substreams[i]} failed to connect")
            
            # Generate ID: ip_substream
            clean_ip = request.rtsp_config.ip_address.replace(".", "_")
            substream = request.rtsp_config.substreams[i]
            # Sanitize substream name for ID
            sub_id = substream.replace("/", "_").replace("\\", "_")
            cam_id = f"rtsp_{clean_ip}_{sub_id}"
            existing = await redis.hget(CAMERA_SOURCES_KEY, cam_id)
            if existing == url:
                sources_to_add[cam_id] = url
                continue
            sources_to_add[cam_id] = url
    else:
        raise HTTPException(status_code=400, detail="Invalid source_type")

    for cam_id, src in sources_to_add.items():
        await redis.hset(CAMERA_SOURCES_KEY, cam_id, src)
        # Also seed default config if not exists
        config_key = f"config:{cam_id}"
        if not await redis.exists(config_key):
             await redis.hset(config_key, mapping={
                "roi": "{}",
                "confidence_threshold": "0.5",
                "iou_threshold": "0.15",
                "hand_dist_px": "80",
                "enabled": "true"
            })
            
    return ConnectResponse(
        status="success",
        message=f"Connected {len(sources_to_add)} stream(s)",
        stream_ids=list(sources_to_add.keys())
    )
