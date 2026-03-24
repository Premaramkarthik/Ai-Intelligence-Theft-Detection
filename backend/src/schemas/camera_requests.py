from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from src.models.camera import CameraStatus, RTSPTransport


class CreateCameraRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    name: str = Field(min_length=2, max_length=120)
    location: str | None = Field(default=None, max_length=255)
    host: str | None = Field(default=None, max_length=255)
    port: int = Field(default=554, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: SecretStr | None = None
    path: str | None = Field(default=None, max_length=255)
    direct_rtsp_url: str | None = Field(default=None, max_length=2048)
    transport: RTSPTransport = RTSPTransport.tcp
    status: CameraStatus = CameraStatus.inactive
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source(self) -> CreateCameraRequest:
        has_components = self.host is not None and self.path is not None
        if not self.direct_rtsp_url and not has_components:
            raise ValueError("Provide either direct_rtsp_url or host + path.")
        return self


class UpdateCameraRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    name: str | None = Field(default=None, min_length=2, max_length=120)
    location: str | None = Field(default=None, max_length=255)
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: SecretStr | None = None
    path: str | None = Field(default=None, max_length=255)
    direct_rtsp_url: str | None = Field(default=None, max_length=2048)
    transport: RTSPTransport | None = None
    status: CameraStatus | None = None
    metadata: dict[str, Any] | None = None
    tags: list[str] | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> UpdateCameraRequest:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided for update.")
        return self


class CameraValidationRequest(BaseModel):
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)


class CameraListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    search: str | None = Field(default=None, max_length=120)
    status: CameraStatus | None = None
