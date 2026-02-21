"""
Signaling service — FastAPI application factory.
Entry point: uvicorn services.signaling.main:app
"""
from __future__ import annotations

import asyncio
import signal

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from libs.shared.logging.logger import get_logger
from libs.shared.core.settings import get_settings
from services.signaling.api.router import api_router

log = get_logger(__name__)
cfg = get_settings()

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


def create_app() -> FastAPI:
    application = FastAPI(
        title="Pipeline Signaling API",
        version="0.2.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount Prometheus metrics at /metrics
    metrics_app = make_asgi_app()
    application.mount("/metrics", metrics_app)

    # API routes
    application.include_router(api_router)

    # Lifespan events
    @application.on_event("startup")
    async def _startup() -> None:
        application.state.redis = aioredis.from_url(cfg.redis_url, decode_responses=True)
        log.info("Signaling service started")

    @application.on_event("shutdown")
    async def _shutdown() -> None:
        from libs.shared.shm.ring_buffer import ReaderCache
        ReaderCache.clear()
        await application.state.redis.aclose()
        log.info("Signaling service stopped")

    return application




app = create_app()
