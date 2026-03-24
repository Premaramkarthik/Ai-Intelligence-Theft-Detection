from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

DataT = TypeVar("DataT")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ApiStatus(str, Enum):
    success = "success"
    error = "error"


class ApiResponse(BaseModel, Generic[DataT]):
    model_config = ConfigDict(use_enum_values=True)

    status: ApiStatus
    message: str
    data: DataT | None = None
    error_code: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    meta: dict[str, Any] | None = None


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PaginatedItems(BaseModel, Generic[DataT]):
    items: list[DataT]
    pagination: PaginationMeta


class HealthComponent(BaseModel):
    status: str
    message: str
    details: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    service: str
    environment: str
    version: str
    uptime_seconds: float
    components: dict[str, HealthComponent]


class WebSocketEnvelope(BaseModel):
    type: str
    topic: str
    message: str
    camera_id: str | None = None
    data: dict[str, Any] | None = None
    timestamp: datetime = Field(default_factory=utc_now)
