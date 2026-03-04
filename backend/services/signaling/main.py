"""
Signaling service — FastAPI application factory.
Entry point: uvicorn services.signaling.main:app
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from shared.logging.logger import get_logger
from shared.core.settings import get_settings
from shared.db.session import DatabaseSession
from services.signaling.api.router import api_router

log = get_logger(__name__)
cfg = get_settings()

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle."""
    # ── Startup ──
    application.state.redis = aioredis.from_url(cfg.redis_url, decode_responses=True)
    application.state.db = DatabaseSession()
    await application.state.db.connect()
    log.info("Signaling service started")
    yield
    # ── Shutdown ──
    from shared.shm.ring_buffer import ReaderCache
    ReaderCache.clear()
    await application.state.db.disconnect()
    await application.state.redis.aclose()
    log.info("Signaling service stopped")


def create_app() -> FastAPI:
    application = FastAPI(
        title="Pipeline Signaling API",
        version="0.3.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    metrics_app = make_asgi_app()
    application.mount("/metrics", metrics_app)
    application.include_router(api_router)

    return application


app = create_app()
