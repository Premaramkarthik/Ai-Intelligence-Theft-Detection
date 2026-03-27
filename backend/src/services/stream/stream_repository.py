from __future__ import annotations

from enum import Enum
from typing import Any

from src.core.db import Database
from src.models.camera import StreamDesiredState, StreamProtocol, StreamRecord, StreamStatus
from src.schemas.stream_responses import StreamEventPayload


class StreamRepository:
    INSERT_STREAM_SQL = "stream/insert_stream.sql"
    GET_STREAM_SQL = "stream/get_stream.sql"
    LIST_STREAMS_SQL = "stream/list_streams.sql"
    UPDATE_STREAM_STATUS_SQL = "stream/update_stream_status.sql"
    APPLY_STREAM_EVENT_SQL = "stream/apply_stream_event.sql"

    def __init__(self, database: Database) -> None:
        self._database = database

    async def upsert_requested_state(
        self,
        camera_id: str,
        stream_id: str,
        status: str,
        desired_state: str,
        protocol: str,
        playback_path: str,
        playlist_path: str,
        metadata: dict[str, Any],
    ) -> StreamRecord:
        row = await self._database.fetchrow_file(
            self.INSERT_STREAM_SQL,
            camera_id,
            stream_id,
            status,
            desired_state,
            protocol,
            playback_path,
            playlist_path,
            metadata,
        )
        return self._map_stream(row)

    async def fetch_by_camera_id(self, camera_id: str) -> StreamRecord | None:
        row = await self._database.fetchrow_file(self.GET_STREAM_SQL, camera_id)
        return self._map_stream(row) if row else None

    async def list_streams(self, camera_id: str | None = None) -> list[StreamRecord]:
        rows = await self._database.fetch_file(self.LIST_STREAMS_SQL, camera_id)
        return [self._map_stream(row) for row in rows]

    async def update_requested_state(
        self,
        camera_id: str,
        status: str,
        desired_state: str,
        metadata: dict[str, Any],
    ) -> StreamRecord | None:
        row = await self._database.fetchrow_file(
            self.UPDATE_STREAM_STATUS_SQL,
            camera_id,
            status,
            desired_state,
            metadata,
        )
        return self._map_stream(row) if row else None

    async def apply_event(self, event: StreamEventPayload) -> StreamRecord:
        row = await self._database.fetchrow_file(
            self.APPLY_STREAM_EVENT_SQL,
            event.camera_id,
            event.stream_id,
            self._enum_value(event.status),
            self._enum_value(event.desired_state),
            self._enum_value(event.protocol),
            event.playback_url,
            event.playlist_path,
            event.process_id,
            event.timestamp,
            event.error_code,
            event.error_message,
            event.restart_count,
            event.reconnect_attempts,
            event.metadata,
        )
        return self._map_stream(row)

    def _map_stream(self, row: Any) -> StreamRecord:
        return StreamRecord(
            camera_id=row["camera_id"],
            stream_id=row["stream_id"],
            status=StreamStatus(row["status"]),
            desired_state=StreamDesiredState(row["desired_state"]),
            protocol=StreamProtocol(row["protocol"]),
            playback_path=row["playback_path"],
            playlist_path=row["playlist_path"],
            worker_pid=row["worker_pid"],
            worker_started_at=row["worker_started_at"],
            last_event_at=row["last_event_at"],
            last_heartbeat_at=row["last_heartbeat_at"],
            last_error_code=row["last_error_code"],
            last_error_message=row["last_error_message"],
            restart_count=row["restart_count"],
            reconnect_attempts=row["reconnect_attempts"],
            metadata=row["metadata"] or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _enum_value(value: str | Enum) -> str:
        return value.value if isinstance(value, Enum) else value
