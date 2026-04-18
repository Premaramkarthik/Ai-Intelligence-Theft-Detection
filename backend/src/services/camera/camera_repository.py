from __future__ import annotations

from typing import Any

from src.core.db import Database
from src.models.camera import (
    CameraRecord,
    CameraStatus,
    RTSPTransport,
    StreamStatus,
    ValidationStatus,
)


class CameraRepository:
    INSERT_CAMERA_SQL = "camera/insert_camera.sql"
    GET_CAMERA_BY_ID_SQL = "camera/get_camera_by_id.sql"
    LIST_CAMERAS_SQL = "camera/list_cameras.sql"
    UPDATE_CAMERA_SQL = "camera/update_camera.sql"
    DELETE_CAMERA_SQL = "camera/delete_camera.sql"
    UPDATE_CAMERA_VALIDATION_SQL = "camera/update_camera_validation.sql"

    def __init__(self, database: Database) -> None:
        self._database = database

    async def insert(
        self,
        camera_id: str,
        name: str,
        location: str | None,
        host: str | None,
        port: int | None,
        username: str | None,
        password: str | None,
        path: str | None,
        direct_rtsp_url: str | None,
        transport: str,
        status: str,
        metadata: dict[str, Any],
        tags: list[str],
    ) -> CameraRecord:
        row = await self._database.fetchrow_file(
            self.INSERT_CAMERA_SQL,
            camera_id,
            name,
            location,
            host,
            port,
            username,
            password,
            path,
            direct_rtsp_url,
            transport,
            status,
            metadata,
            tags,
        )
        return self._map_camera(row)

    async def fetch_by_id(self, camera_id: str) -> CameraRecord | None:
        row = await self._database.fetchrow_file(self.GET_CAMERA_BY_ID_SQL, camera_id)
        return self._map_camera(row) if row else None

    async def list(
        self,
        status: str | None,
        search: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[CameraRecord], int]:
        rows = await self._database.fetch_file(
            self.LIST_CAMERAS_SQL,
            status,
            search,
            limit,
            offset,
        )
        if not rows and offset > 0:
            total_probe_rows = await self._database.fetch_file(
                self.LIST_CAMERAS_SQL,
                status,
                search,
                1,
                0,
            )
            total_items = int(total_probe_rows[0]["total_count"]) if total_probe_rows else 0
            return [], total_items
        cameras = [self._map_camera(row) for row in rows]
        total_items = int(rows[0]["total_count"]) if rows else 0
        return cameras, total_items

    async def delete(self, camera_id: str) -> bool:
        deleted_camera_id = await self._database.fetchval_file(
            self.DELETE_CAMERA_SQL,
            camera_id,
        )
        return deleted_camera_id is not None

    async def update(
        self,
        camera_id: str,
        name: str,
        location: str | None,
        host: str | None,
        port: int | None,
        username: str | None,
        password: str | None,
        path: str | None,
        direct_rtsp_url: str | None,
        transport: str,
        status: str,
        metadata: dict[str, Any],
        tags: list[str],
    ) -> CameraRecord | None:
        row = await self._database.fetchrow_file(
            self.UPDATE_CAMERA_SQL,
            camera_id,
            name,
            location,
            host,
            port,
            username,
            password,
            path,
            direct_rtsp_url,
            transport,
            status,
            metadata,
            tags,
        )
        return self._map_camera(row) if row else None

    async def update_validation_status(
        self,
        camera_id: str,
        validation_status: str,
        validation_message: str,
    ) -> CameraRecord | None:
        row = await self._database.fetchrow_file(
            self.UPDATE_CAMERA_VALIDATION_SQL,
            camera_id,
            validation_status,
            validation_message,
        )
        return self._map_camera(row) if row else None

    def _map_camera(self, row: Any) -> CameraRecord:
        return CameraRecord(
            id=row["id"],
            name=row["name"],
            location=row["location"],
            host=row["host"],
            port=row["port"],
            username=row["username"],
            password=row["password"],
            path=row["path"],
            direct_rtsp_url=row["direct_rtsp_url"],
            transport=RTSPTransport(row["transport"]),
            status=CameraStatus(row["status"]),
            metadata=row["metadata"] or {},
            tags=list(row["tags"] or []),
            last_validated_at=row["last_validated_at"],
            last_validation_status=ValidationStatus(row["last_validation_status"] or "unknown"),
            last_validation_message=row["last_validation_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            stream_status=StreamStatus(row["stream_status"]) if row["stream_status"] else None,
            stream_metadata=row["stream_metadata"] or {},
        )
