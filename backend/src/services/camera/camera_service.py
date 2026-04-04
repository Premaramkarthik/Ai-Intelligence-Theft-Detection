from __future__ import annotations

from enum import Enum
from math import ceil
from uuid import uuid4

from src.core.exceptions.camera.camera_exceptions import (
    CameraNotFoundException,
    CameraSourceUnavailableException,
    CameraValidationException,
)
from src.core.logger.logger import get_logger
from src.models.camera import CameraRecord, ValidationStatus
from src.schemas.camera_requests import CameraListQuery, CreateCameraRequest, UpdateCameraRequest
from src.schemas.camera_responses import CameraResponse, CameraValidationResponse
from src.schemas.common import PaginatedItems, PaginationMeta
from src.services.camera.camera_repository import CameraRepository
from src.services.camera.camera_validator import CameraValidationResult, CameraValidator
from src.services.realtime_video.mediamtx_service import MediaMtxService
from src.utils.ffmpeg import build_rtsp_url_from_camera, mask_rtsp_url


class CameraService:
    def __init__(
        self,
        repository: CameraRepository,
        validator: CameraValidator,
        mediamtx_service: MediaMtxService | None = None,
    ) -> None:
        """Create the camera service with optional MediaMTX config synchronization."""

        self._repository = repository
        self._validator = validator
        self._mediamtx_service = mediamtx_service
        self._logger = get_logger(__name__)

    async def create_camera(self, payload: CreateCameraRequest) -> CameraResponse:
        """Create a camera record and refresh the generated MediaMTX config."""

        camera = await self._repository.insert(
            camera_id=f"cam_{uuid4().hex[:12]}",
            name=payload.name,
            location=payload.location,
            host=payload.host,
            port=payload.port,
            username=payload.username,
            password=payload.password.get_secret_value() if payload.password else None,
            path=payload.path,
            direct_rtsp_url=payload.direct_rtsp_url,
            transport=self._enum_value(payload.transport),
            status=self._enum_value(payload.status),
            metadata=payload.metadata,
            tags=payload.tags,
        )
        await self._sync_mediamtx_config()
        return self._to_response(camera)

    async def list_cameras(self, query: CameraListQuery) -> PaginatedItems[CameraResponse]:
        offset = (query.page - 1) * query.page_size
        cameras, total_items = await self._repository.list(
            status=self._enum_value(query.status) if query.status else None,
            search=query.search,
            limit=query.page_size,
            offset=offset,
        )
        total_pages = ceil(total_items / query.page_size) if total_items else 0
        return PaginatedItems[CameraResponse](
            items=[self._to_response(camera) for camera in cameras],
            pagination=PaginationMeta(
                page=query.page,
                page_size=query.page_size,
                total_items=total_items,
                total_pages=total_pages,
                has_next=query.page < total_pages,
                has_previous=query.page > 1,
            ),
        )

    async def list_all_camera_records(self) -> list[CameraRecord]:
        page = 1
        page_size = 100
        cameras: list[CameraRecord] = []
        while True:
            page_cameras, total_items = await self._repository.list(
                status=None,
                search=None,
                limit=page_size,
                offset=(page - 1) * page_size,
            )
            cameras.extend(page_cameras)
            if len(cameras) >= total_items or not page_cameras:
                break
            page += 1
        return cameras

    async def get_camera(self, camera_id: str) -> CameraResponse:
        camera = await self.get_camera_record(camera_id)
        return self._to_response(camera)

    async def get_camera_record(self, camera_id: str) -> CameraRecord:
        camera = await self._repository.fetch_by_id(camera_id)
        if camera is None:
            raise CameraNotFoundException(camera_id)
        return camera

    async def update_camera(self, camera_id: str, payload: UpdateCameraRequest) -> CameraResponse:
        """Update a camera record and refresh the generated MediaMTX config."""

        existing = await self.get_camera_record(camera_id)
        updates = payload.model_dump(exclude_unset=True)
        if "password" in updates:
            updates["password"] = payload.password.get_secret_value() if payload.password else None

        merged = {
            "name": updates.get("name", existing.name),
            "location": updates.get("location", existing.location),
            "host": updates.get("host", existing.host),
            "port": updates.get("port", existing.port),
            "username": updates.get("username", existing.username),
            "password": updates.get("password", existing.password),
            "path": updates.get("path", existing.path),
            "direct_rtsp_url": updates.get("direct_rtsp_url", existing.direct_rtsp_url),
            "transport": self._enum_value(
                updates.get("transport", existing.transport),
            ),
            "status": self._enum_value(
                updates.get("status", existing.status),
            ),
            "metadata": updates.get("metadata", existing.metadata),
            "tags": updates.get("tags", existing.tags),
        }

        if not merged["direct_rtsp_url"] and not (merged["host"] and merged["path"]):
            raise CameraValidationException(
                "Camera must keep either direct_rtsp_url or host + path."
            )

        updated = await self._repository.update(
            camera_id=camera_id,
            name=merged["name"],
            location=merged["location"],
            host=merged["host"],
            port=merged["port"],
            username=merged["username"],
            password=merged["password"],
            path=merged["path"],
            direct_rtsp_url=merged["direct_rtsp_url"],
            transport=merged["transport"],
            status=merged["status"],
            metadata=merged["metadata"],
            tags=merged["tags"],
        )
        if updated is None:
            raise CameraNotFoundException(camera_id)
        await self._sync_mediamtx_config()
        return self._to_response(updated)

    async def delete_camera(self, camera_id: str) -> None:
        """Delete a camera record and refresh the generated MediaMTX config."""

        deleted = await self._repository.delete(camera_id)
        if not deleted:
            raise CameraNotFoundException(camera_id)
        await self._sync_mediamtx_config()

    async def validate_camera(
        self,
        camera_id: str,
        timeout_seconds: int | None = None,
    ) -> CameraValidationResponse:
        camera = await self.get_camera_record(camera_id)
        target_camera, validation = await self._validate_and_persist(camera, timeout_seconds)
        return CameraValidationResponse(
            camera_id=target_camera.id,
            camera_name=target_camera.name,
            is_reachable=validation.is_reachable,
            code=validation.code,
            message=validation.message,
            resolved_rtsp_url_preview=validation.resolved_rtsp_url_preview,
            latency_ms=validation.latency_ms,
            details=validation.details,
            validated_at=validation.validated_at,
        )

    async def ensure_camera_reachable(
        self,
        camera_id: str,
        timeout_seconds: int | None = None,
    ) -> CameraRecord:
        camera = await self.get_camera_record(camera_id)
        validated_camera, validation = await self._validate_and_persist(camera, timeout_seconds)
        if validation.is_reachable:
            return validated_camera

        raise CameraSourceUnavailableException(
            camera_id=camera_id,
            message=validation.message,
            details={
                "validation_code": validation.code,
                "resolved_rtsp_url_preview": validation.resolved_rtsp_url_preview,
                "latency_ms": validation.latency_ms,
                "validation_details": validation.details,
            },
        )

    def _to_response(self, camera: CameraRecord) -> CameraResponse:
        try:
            rtsp_preview = mask_rtsp_url(build_rtsp_url_from_camera(camera))
        except ValueError:
            rtsp_preview = ""

        return CameraResponse(
            id=camera.id,
            name=camera.name,
            location=camera.location,
            host=camera.host,
            port=camera.port,
            path=camera.path,
            source_mode="direct_url" if camera.direct_rtsp_url else "components",
            rtsp_url_preview=rtsp_preview,
            transport=camera.transport,
            status=camera.status,
            stream_status=camera.stream_status,
            has_credentials=bool(camera.username),
            metadata=camera.metadata,
            tags=camera.tags,
            last_validated_at=camera.last_validated_at,
            last_validation_status=camera.last_validation_status,
            last_validation_message=camera.last_validation_message,
            created_at=camera.created_at,
            updated_at=camera.updated_at,
        )

    @staticmethod
    def _enum_value(value: str | Enum) -> str:
        return value.value if isinstance(value, Enum) else value

    async def _sync_mediamtx_config(self) -> None:
        """Regenerate the MediaMTX config file from the current camera inventory."""

        if self._mediamtx_service is None:
            return
        try:
            cameras = await self.list_all_camera_records()
            await self._mediamtx_service.sync_config(cameras)
        except Exception as exc:  # pylint: disable=broad-except
            self._logger.warning(
                "Failed to regenerate MediaMTX config after camera change: %s",
                exc,
            )

    async def _validate_and_persist(
        self,
        camera: CameraRecord,
        timeout_seconds: int | None = None,
    ) -> tuple[CameraRecord, CameraValidationResult]:
        validation = await self._validator.validate(camera, timeout_seconds)
        validation_status = (
            ValidationStatus.reachable.value
            if validation.is_reachable
            else ValidationStatus.unreachable.value
        )
        updated = await self._repository.update_validation_status(
            camera_id=camera.id,
            validation_status=validation_status,
            validation_message=validation.message,
        )
        return updated or camera, validation
