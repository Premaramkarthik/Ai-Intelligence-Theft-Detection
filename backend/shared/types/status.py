from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from shared.types.events import MessageType


class GpuStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool = False
    total: int | None = None
    used: int | None = None
    free: int | None = None
    utilization: int | None = None
    temperature: int | None = None
    error: str | None = None


class SystemResourceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu_usage: float = 0.0
    ram_usage: float = 0.0


class CameraFleetStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_configured: int = 0
    active_streaming: int = 0


class SystemStatusMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_type: MessageType = Field(default=MessageType.STATUS)
    status: str
    redis: str | None = None
    cameras: CameraFleetStatus | None = None
    gpu: GpuStatus = Field(default_factory=GpuStatus)
    system: SystemResourceStatus = Field(default_factory=SystemResourceStatus)
    uptime: float | None = None
    ts: float | None = None
