"""GET /health — Liveness + Readiness probes for Kubernetes."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from services.signaling.api.deps import get_redis

router = APIRouter()


@router.get("/health/live")
async def liveness() -> dict:
    """Liveness probe — is the process alive?"""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(redis=Depends(get_redis)) -> dict:
    """Readiness probe — can we serve traffic? Checks Redis connectivity."""
    try:
        await asyncio.wait_for(redis.ping(), timeout=1.0)
        return {"status": "ready", "redis": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="Redis not available")


@router.get("/health")
async def health_check() -> dict:
    """Basic health check (backward-compatible)."""
    return {"status": "ok"}
