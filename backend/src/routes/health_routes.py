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
    uptime_seconds = round(time() - container.started_at_epoch, 2)
    kafka_snapshot = container.tracking_kafka_producer.health_snapshot()
    stream_consumer = getattr(container, "stream_event_consumer", None)
    stream_consumer_snapshot = (
        stream_consumer.health_snapshot() if stream_consumer is not None else None
    )
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
            "tracking_kafka_producer": HealthComponent(
                status="ok" if kafka_snapshot["healthy"] else "error",
                message=(
                    "Kafka producer is healthy."
                    if kafka_snapshot["healthy"]
                    else "Kafka producer is unavailable."
                ),
                details=kafka_snapshot,
            ),
            "stream_event_consumer": HealthComponent(
                status=(
                    "ok"
                    if stream_consumer_snapshot is None
                    or stream_consumer_snapshot["healthy"]
                    else "error"
                ),
                message=(
                    "Kafka stream consumer is healthy."
                    if stream_consumer_snapshot is None
                    or stream_consumer_snapshot["healthy"]
                    else "Kafka stream consumer is unavailable."
                ),
                details=stream_consumer_snapshot,
            ),
            "inference_manager": HealthComponent(
                status="ok",
                message="Inference manager is available.",
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
    "/logs",
    response_model=ApiResponse[dict[str, list[str]]],
    summary="Get recent system logs",
)
async def get_logs(lines: int = 50) -> dict[str, Any]:
    from pathlib import Path
    log_dir = Path.cwd() / "logs"
    logs = {}
    if log_dir.exists():
        for process_dir in log_dir.iterdir():
            if process_dir.is_dir():
                log_files = sorted(process_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
                if log_files:
                    latest_log = log_files[0]
                    try:
                        with open(latest_log, "r", encoding="utf-8") as f:
                            content = f.readlines()
                            logs[process_dir.name] = [line.strip() for line in content[-lines:]]
                    except Exception as e:
                        logs[process_dir.name] = [f"Error reading log: {e}"]
    return build_success_payload("Logs fetched successfully.", logs)

