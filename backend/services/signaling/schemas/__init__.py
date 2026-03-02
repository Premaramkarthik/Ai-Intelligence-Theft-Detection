"""
services.signaling.schemas — Pydantic request/response models.

    from services.signaling.schemas import TokenResponse, ROIConfigRequest, ROIConfigResponse
"""
from services.signaling.schemas.auth import TokenResponse
from services.signaling.schemas.camera import ROIConfigRequest, ROIConfigResponse

__all__ = ["TokenResponse", "ROIConfigRequest", "ROIConfigResponse"]
