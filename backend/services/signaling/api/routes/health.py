"""Health and readiness endpoints."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from services.signaling.api.deps import get_redis
from shared.core.settings import get_settings

router = APIRouter()


@router.get("/health/live")
async def liveness() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(request: Request, redis=Depends(get_redis)) -> dict:
    settings = get_settings()
    try:
        await asyncio.wait_for(redis.ping(), timeout=1.0)
        await asyncio.wait_for(request.app.state.db.get_pool().fetchval("SELECT 1"), timeout=1.0)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Dependency unavailable: {exc}") from exc

    return {
        "status": "ready",
        "redis": "ok",
        "postgres": "ok",
        "auth_configured": bool(settings.jwt_secret and settings.admin_username and settings.admin_password),
        "model_configured": bool(settings.model_engine_path),
    }


@router.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}
