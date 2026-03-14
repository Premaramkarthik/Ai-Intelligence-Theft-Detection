"""
Signaling service - FastAPI application factory.
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

from services.signaling.api.router import api_router
from shared.core.settings import get_settings
from shared.db.session import DatabaseSession
from shared.logging.logger import get_logger

log = get_logger(__name__)
cfg = get_settings()
limiter = Limiter(key_func=get_remote_address)


def _cors_origins() -> list[str]:
    origins = [origin.strip() for origin in cfg.cors_origins.split(",") if origin.strip()]
    return origins or ["http://localhost:3000", "http://127.0.0.1:3000"]


def _validate_security_settings() -> None:
    if cfg.app_env != "development":
        if "*" in _cors_origins():
            raise RuntimeError("Wildcard CORS is not allowed outside development")
        if not cfg.jwt_secret or not cfg.admin_username or not cfg.admin_password:
            raise RuntimeError("JWT/admin credentials must be configured outside development")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle."""
    _validate_security_settings()
    application.state.redis = aioredis.from_url(cfg.redis_url, decode_responses=True)
    await application.state.redis.ping()

    application.state.db = DatabaseSession()
    await application.state.db.connect()
    await application.state.db.get_pool().fetchval("SELECT 1")

    log.info("Signaling service started")
    yield

    from shared.shm.ring_buffer import ReaderCache

    ReaderCache.clear()
    await application.state.db.disconnect()
    await application.state.redis.aclose()
    log.info("Signaling service stopped")


def create_app() -> FastAPI:
    application = FastAPI(
        title="Pipeline Signaling API",
        version="0.4.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    metrics_app = make_asgi_app()
    application.mount("/metrics", metrics_app)
    application.include_router(api_router)
    return application


app = create_app()
