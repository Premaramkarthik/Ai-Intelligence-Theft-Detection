from __future__ import annotations

from time import time
from typing import Any

from fastapi import APIRouter, Request

from src.schemas.common import ApiResponse, HealthComponent, HealthResponse
from src.utils.response import build_success_payload

router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "",
    response_model=ApiResponse[HealthResponse],
    summary="Get platform health",
)
async def health(request: Request) -> dict[str, Any]:
    container = request.app.state.container
    db_ok = await container.database.ping()
    kafka = container.kafka_consumer.health_snapshot()
    mediamtx = container.mediamtx_service.health_snapshot()
    uptime_seconds = round(time() - container.started_at_epoch, 2)
    payload = HealthResponse(
        service=container.settings.app_name,
        environment=container.settings.environment,
        version=container.settings.app_version,
        uptime_seconds=uptime_seconds,
        components={
            "database": HealthComponent(
                status="ok" if db_ok else "error",
                message="Database connection is healthy." if db_ok else "Database ping failed.",
            ),
            "kafka": HealthComponent(
                status="ok" if kafka["healthy"] else "degraded",
                message=(
                    "Kafka consumer is healthy."
                    if kafka["healthy"]
                    else "Kafka consumer is degraded."
                ),
                details={"last_error": kafka["last_error"]},
            ),
            "workers": HealthComponent(
                status="ok",
                message="Worker registry is available.",
                details={"active_workers": container.stream_manager.active_worker_count()},
            ),
            "mediamtx": HealthComponent(
                status="ok" if mediamtx.healthy else "degraded",
                message=(
                    "MediaMTX is ready."
                    if mediamtx.healthy
                    else "MediaMTX is not ready."
                ),
                details={
                    "managed": mediamtx.managed,
                    "externally_managed": mediamtx.externally_managed,
                    "config_path": mediamtx.config_path,
                    "last_error": mediamtx.last_error,
                },
            ),
        },
    )
    return build_success_payload("Health fetched successfully.", payload.model_dump(mode="json"))


@router.get(
    "/db",
    response_model=ApiResponse[HealthComponent],
    summary="Check database health",
)
async def health_db(request: Request) -> dict[str, Any]:
    is_healthy = await request.app.state.container.database.ping()
    component = HealthComponent(
        status="ok" if is_healthy else "error",
        message="Database connection is healthy." if is_healthy else "Database ping failed.",
    )
    return build_success_payload(
        "Database health fetched successfully.",
        component.model_dump(mode="json"),
    )


@router.get(
    "/stream/{camera_id}",
    response_model=ApiResponse[HealthComponent],
    summary="Check stream health",
)
async def health_stream(camera_id: str, request: Request) -> dict[str, Any]:
    component = await request.app.state.container.stream_service.get_stream_health(camera_id)
    return build_success_payload(
        "Stream health fetched successfully.",
        component.model_dump(mode="json"),
    )
