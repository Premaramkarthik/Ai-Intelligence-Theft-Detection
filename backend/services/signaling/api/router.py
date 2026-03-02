"""Central API router — aggregates all route modules."""
from fastapi import APIRouter

from services.signaling.api.routes import auth, camera, config, events, health, cameras, alerts
from services.signaling.ws import camera_stream, logs, predictions

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(config.router, prefix="/api", tags=["config"])
api_router.include_router(camera.router, prefix="/api", tags=["camera"])
api_router.include_router(cameras.router, prefix="/api/cameras", tags=["cameras"])
api_router.include_router(events.router, prefix="/api", tags=["events"])
api_router.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
api_router.include_router(predictions.router, tags=["ws"])
api_router.include_router(camera_stream.router, tags=["ws"])
api_router.include_router(logs.router, tags=["ws"])
