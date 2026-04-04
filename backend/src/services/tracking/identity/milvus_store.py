"""Milvus-backed identity store for persistent cross-camera re-identification."""

# pylint: disable=too-many-arguments,too-many-locals,duplicate-code

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from time import perf_counter, time
from urllib.parse import urlparse
from uuid import uuid4

import numpy as np
from pymilvus import DataType, MilvusClient

from src.observability.metrics import MetricsRecorder, NullMetricsRecorder


@dataclass(slots=True, frozen=True)
class IdentityMatch:
    """Result of matching a local track embedding against the persistent store."""

    identity_id: str
    matched_existing: bool
    similarity: float


@dataclass(slots=True, frozen=True)
class IdentityStoreHealthSnapshot:
    """Health snapshot for the Milvus-backed identity store."""

    healthy: bool
    last_error: str | None


class MilvusIdentityStore:  # pylint: disable=too-many-instance-attributes
    """Persist and retrieve cross-camera identities with Milvus."""

    def __init__(
        self,
        *,
        uri: str,
        collection_name: str,
        embedding_dimension: int,
        timeout_seconds: float,
        similarity_threshold: float,
        search_limit: int,
        token: str | None = None,
        metrics_recorder: MetricsRecorder | None = None,
    ) -> None:  # pylint: disable=too-many-arguments
        self._uri = uri
        self._collection_name = collection_name
        self._embedding_dimension = embedding_dimension
        self._timeout_seconds = timeout_seconds
        self._similarity_threshold = similarity_threshold
        self._search_limit = max(1, search_limit)
        self._token = token
        self._metrics_recorder = metrics_recorder or NullMetricsRecorder()
        self._client: MilvusClient | None = None
        self._lock = Lock()
        self._healthy = True
        self._last_error: str | None = None

    def ensure_ready(self) -> None:
        """Create the collection and indexes if they do not already exist."""

        try:
            with self._lock:
                client = self._get_client()
                self._ensure_collection_ready(client)
        except Exception as exc:  # pylint: disable=broad-except
            self._mark_unhealthy(exc)
            raise
        self._mark_healthy()

    def resolve_identity(
        self,
        *,
        camera_id: str,
        stream_name: str,
        local_track_id: str,
        embedding: np.ndarray,
    ) -> IdentityMatch:  # pylint: disable=too-many-locals
        """Search for an existing identity and upsert the latest observation."""

        vector = _normalize_embedding(embedding, self._embedding_dimension)
        now_ts = int(time() * 1000)
        lookup_started_at = perf_counter()
        try:
            with self._lock:
                client = self._get_client()
                self._ensure_collection_ready(client)
                search_results = client.search(
                    collection_name=self._collection_name,
                    data=[vector.tolist()],
                    limit=self._search_limit,
                    output_fields=[
                        "identity_id",
                        "camera_id",
                        "stream_name",
                        "last_seen_ts",
                    ],
                    search_params={"metric_type": "COSINE"},
                    timeout=self._timeout_seconds,
                )

                best_match = search_results[0][0] if search_results and search_results[0] else None
                similarity = float(best_match["distance"]) if best_match else 0.0
                if best_match is not None and similarity >= self._similarity_threshold:
                    identity_id = _extract_identity_id(best_match)
                    matched_existing = True
                else:
                    identity_id = f"person_{uuid4().hex[:12]}"
                    matched_existing = False

                payload = {
                    "identity_id": identity_id,
                    "embedding": vector.tolist(),
                    "camera_id": camera_id,
                    "stream_name": stream_name,
                    "local_track_id": local_track_id,
                    "first_seen_ts": (
                        now_ts
                        if not matched_existing
                        else _first_seen_ts(
                            client,
                            self._collection_name,
                            identity_id,
                            now_ts,
                            self._timeout_seconds,
                        )
                    ),
                    "last_seen_ts": now_ts,
                }
                client.upsert(collection_name=self._collection_name, data=[payload])
        except Exception as exc:  # pylint: disable=broad-except
            self._mark_unhealthy(exc)
            raise

        self._mark_healthy()
        self._metrics_recorder.observe_tracking_identity_lookup_duration(
            camera_id,
            perf_counter() - lookup_started_at,
        )
        self._metrics_recorder.increment_tracking_identity_resolution(
            camera_id,
            matched_existing,
        )
        return IdentityMatch(
            identity_id=identity_id,
            matched_existing=matched_existing,
            similarity=similarity,
        )

    def refresh_identity(
        self,
        *,
        identity_id: str,
        camera_id: str,
        stream_name: str,
        local_track_id: str,
        embedding: np.ndarray,
    ) -> None:  # pylint: disable=too-many-arguments
        """Refresh the latest embedding and metadata for an already assigned identity."""

        vector = _normalize_embedding(embedding, self._embedding_dimension)
        now_ts = int(time() * 1000)
        try:
            with self._lock:
                client = self._get_client()
                self._ensure_collection_ready(client)
                client.upsert(
                    collection_name=self._collection_name,
                    data=[
                        {
                            "identity_id": identity_id,
                            "embedding": vector.tolist(),
                            "camera_id": camera_id,
                            "stream_name": stream_name,
                            "local_track_id": local_track_id,
                            "first_seen_ts": _first_seen_ts(
                                client,
                                self._collection_name,
                                identity_id,
                                now_ts,
                                self._timeout_seconds,
                            ),
                            "last_seen_ts": now_ts,
                        },
                    ],
                    timeout=self._timeout_seconds,
                )
        except Exception as exc:  # pylint: disable=broad-except
            self._mark_unhealthy(exc)
            raise
        self._mark_healthy()

    def close(self) -> None:
        """Release the client connection."""

        with self._lock:
            if self._client is None:
                return
            self._client.close()
            self._client = None

    def health_snapshot(self) -> IdentityStoreHealthSnapshot:
        """Return the latest observed health state for the identity store."""

        return IdentityStoreHealthSnapshot(
            healthy=self._healthy,
            last_error=self._last_error,
        )

    def _get_client(self) -> MilvusClient:
        if self._client is not None:
            return self._client

        parsed = urlparse(self._uri)
        if parsed.scheme in {"http", "https", "tcp"}:
            self._client = MilvusClient(
                uri=self._uri,
                token=self._token,
                timeout=self._timeout_seconds,
            )
            return self._client

        local_path = Path(self._uri)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self._client = MilvusClient(str(local_path), timeout=self._timeout_seconds)
        return self._client

    def _ensure_collection_ready(self, client: MilvusClient) -> None:
        if client.has_collection(
            self._collection_name,
            timeout=self._timeout_seconds,
        ):
            return

        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(
            field_name="identity_id",
            datatype=DataType.VARCHAR,
            is_primary=True,
            max_length=128,
        )
        schema.add_field(
            field_name="embedding",
            datatype=DataType.FLOAT_VECTOR,
            dim=self._embedding_dimension,
        )
        schema.add_field(
            field_name="camera_id",
            datatype=DataType.VARCHAR,
            max_length=128,
        )
        schema.add_field(
            field_name="stream_name",
            datatype=DataType.VARCHAR,
            max_length=128,
        )
        schema.add_field(
            field_name="local_track_id",
            datatype=DataType.VARCHAR,
            max_length=128,
        )
        schema.add_field(
            field_name="first_seen_ts",
            datatype=DataType.INT64,
        )
        schema.add_field(
            field_name="last_seen_ts",
            datatype=DataType.INT64,
        )

        index_params = client.prepare_index_params()
        index_params.add_index(field_name="identity_id")
        index_params.add_index(
            field_name="embedding",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        client.create_collection(
            collection_name=self._collection_name,
            schema=schema,
            index_params=index_params,
            timeout=self._timeout_seconds,
        )

    def _mark_healthy(self) -> None:
        self._healthy = True
        self._last_error = None
        self._metrics_recorder.set_dependency_health("milvus_identity_store", True)

    def _mark_unhealthy(self, exc: Exception) -> None:
        with self._lock:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:  # pylint: disable=broad-except
                    pass
                self._client = None
        self._healthy = False
        self._last_error = str(exc)
        self._metrics_recorder.set_dependency_health("milvus_identity_store", False)


def _normalize_embedding(embedding: np.ndarray, expected_dimension: int) -> np.ndarray:
    vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
    if vector.size != expected_dimension:
        raise ValueError(
            f"Expected embedding dimension {expected_dimension}, got {vector.size}.",
        )
    norm = float(np.linalg.norm(vector))
    if norm <= 0:
        raise ValueError("Embedding norm must be greater than zero.")
    return vector / norm


def _first_seen_ts(
    client: MilvusClient,
    collection_name: str,
    identity_id: str,
    fallback: int,
    timeout_seconds: float,
) -> int:
    result = client.get(
        collection_name=collection_name,
        ids=[identity_id],
        output_fields=["first_seen_ts"],
        timeout=timeout_seconds,
    )
    if not result:
        return fallback
    return int(result[0].get("first_seen_ts", fallback))


def _extract_identity_id(best_match: dict[str, object]) -> str:
    """Return the primary identity value from the different Milvus search result shapes."""

    direct_id = best_match.get("id")
    if direct_id is not None:
        return str(direct_id)

    named_id = best_match.get("identity_id")
    if named_id is not None:
        return str(named_id)

    entity = best_match.get("entity")
    if isinstance(entity, dict) and entity.get("identity_id") is not None:
        return str(entity["identity_id"])

    raise KeyError("identity_id")
