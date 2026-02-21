"""GET /health"""
from fastapi import APIRouter
from libs.shared.logging.logger import get_logger

router = APIRouter()
log = get_logger(__name__)


@router.get("/health")
async def health() -> dict:
    log.debug("Health check")
    return {"status": "ok", "service": "signaling"}
