"""Global identity assignment and lifecycle tracking over Milvus search results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from time import perf_counter

from src.opencv_pipeline.contracts import (
    IdentityEventType,
    IdentityLifecycleEvent,
    ProcessedFrame,
    TrackIdentityState,
    TrackedObject,
    utc_now,
)
from src.services.tracking.identity.milvus_store import (
    BatchResolveRequest,
    IdentityMatch,
    MilvusIdentityStore,
)


@dataclass(slots=True)
class _TrackAssignmentState:
    persistent_id: str
    stream_name: str
    local_track_id: str
    left: int
    top: int
    width: int
    height: int
    world_x: float | None
    world_y: float | None
    last_seen: datetime


class IdentityAssignmentService:
    """Resolve cross-camera identities and emit lifecycle events."""

    def __init__(
        self,
        identity_store: MilvusIdentityStore,
        *,
        identity_ttl_seconds: float,
    ) -> None:
        self._identity_store = identity_store
        self._identity_ttl_seconds = identity_ttl_seconds
        self._track_assignments: dict[tuple[str, str], _TrackAssignmentState] = {}

    def ensure_ready(self) -> None:
        """Ensure the backing Milvus collection exists."""

        self._identity_store.ensure_ready()

    async def assign(
        self,
        assignments: list[tuple[ProcessedFrame, list[TrackedObject]]],
    ) -> tuple[list[IdentityLifecycleEvent], float]:
        """Resolve embeddings, mutate tracks in place, and return lifecycle events."""

        started_at = perf_counter()
        requests: list[BatchResolveRequest] = []
        indexed_tracks: list[TrackedObject] = []
        for processed_frame, tracks in assignments:
            for track in tracks:
                if track.embedding is None:
                    continue
                requests.append(
                    BatchResolveRequest(
                        camera_id=track.camera_id,
                        stream_name=processed_frame.packet.stream_name,
                        local_track_id=track.track_id,
                        embedding=track.embedding,
                    )
                )
                indexed_tracks.append(track)

        lifecycle_events: list[IdentityLifecycleEvent] = []
        if requests:
            matches = await self._identity_store.batch_resolve(requests)
            lifecycle_events.extend(self._apply_matches(indexed_tracks, matches))

        lifecycle_events.extend(self.expire_stale())
        return lifecycle_events, (perf_counter() - started_at) * 1000.0

    def expire_stale(self, reference_time: datetime | None = None) -> list[IdentityLifecycleEvent]:
        """Expire stale local-track assignments that have exceeded the TTL."""

        now = reference_time or utc_now()
        expired: list[IdentityLifecycleEvent] = []
        stale_keys: list[tuple[str, str]] = []
        for key, state in self._track_assignments.items():
            age_seconds = (now - state.last_seen).total_seconds()
            if age_seconds < self._identity_ttl_seconds:
                continue
            stale_keys.append(key)
            expired.append(
                IdentityLifecycleEvent(
                    event_type=IdentityEventType.expired,
                    camera_id=key[0],
                    stream_name=state.stream_name,
                    local_track_id=state.local_track_id,
                    persistent_id=state.persistent_id,
                    previous_persistent_id=None,
                    matched_existing=True,
                    similarity=None,
                    occurred_at=now,
                    left=state.left,
                    top=state.top,
                    width=state.width,
                    height=state.height,
                    world_x=state.world_x,
                    world_y=state.world_y,
                )
            )
        for key in stale_keys:
            self._track_assignments.pop(key, None)
        return expired

    def remove_camera(
        self,
        camera_id: str,
        reference_time: datetime | None = None,
    ) -> list[IdentityLifecycleEvent]:
        """Expire and remove all local identity assignments for a removed camera."""

        now = reference_time or utc_now()
        removed: list[IdentityLifecycleEvent] = []
        stale_keys = [
            key
            for key in self._track_assignments
            if key[0] == camera_id
        ]
        for key in stale_keys:
            state = self._track_assignments.pop(key)
            removed.append(
                IdentityLifecycleEvent(
                    event_type=IdentityEventType.expired,
                    camera_id=key[0],
                    stream_name=state.stream_name,
                    local_track_id=state.local_track_id,
                    persistent_id=state.persistent_id,
                    previous_persistent_id=None,
                    matched_existing=True,
                    similarity=None,
                    occurred_at=now,
                    left=state.left,
                    top=state.top,
                    width=state.width,
                    height=state.height,
                    world_x=state.world_x,
                    world_y=state.world_y,
                )
            )
        return removed

    def close(self) -> None:
        """Close the underlying identity store client."""

        self._identity_store.close()

    def _apply_matches(
        self,
        tracks: list[TrackedObject],
        matches: list[IdentityMatch],
    ) -> list[IdentityLifecycleEvent]:
        now = utc_now()
        events: list[IdentityLifecycleEvent] = []
        for track, match in zip(tracks, matches):
            key = (track.camera_id, track.track_id)
            previous = self._track_assignments.get(key)

            track.persistent_id = match.identity_id
            track.similarity = match.similarity
            if previous is None:
                track.persistent_id_state = TrackIdentityState.assigned
                event_type = (
                    IdentityEventType.created
                    if not match.matched_existing
                    else IdentityEventType.updated
                )
                previous_persistent_id = None
            elif previous.persistent_id != match.identity_id:
                track.persistent_id_state = TrackIdentityState.merged
                event_type = IdentityEventType.merged
                previous_persistent_id = previous.persistent_id
            else:
                track.persistent_id_state = TrackIdentityState.assigned
                event_type = IdentityEventType.updated
                previous_persistent_id = None

            events.append(
                IdentityLifecycleEvent(
                    event_type=event_type,
                    camera_id=track.camera_id,
                    stream_name=track.stream_name,
                    local_track_id=track.track_id,
                    persistent_id=match.identity_id,
                    previous_persistent_id=previous_persistent_id,
                    matched_existing=match.matched_existing,
                    similarity=match.similarity,
                    occurred_at=now,
                    left=track.left,
                    top=track.top,
                    width=track.width,
                    height=track.height,
                    world_x=track.world_x,
                    world_y=track.world_y,
                )
            )
            self._track_assignments[key] = _TrackAssignmentState(
                persistent_id=match.identity_id,
                stream_name=track.stream_name,
                local_track_id=track.track_id,
                left=track.left,
                top=track.top,
                width=track.width,
                height=track.height,
                world_x=track.world_x,
                world_y=track.world_y,
                last_seen=now,
            )
        return events
