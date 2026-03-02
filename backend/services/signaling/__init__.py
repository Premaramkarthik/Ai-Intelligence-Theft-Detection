"""
services.signaling — FastAPI signaling server (REST + WebSocket).

    from services.signaling import api_router
"""
from services.signaling.api.router import api_router

__all__ = ["api_router"]
