# Inference Integration Plan — Post Tracker Bottleneck Remediation

**Status:** Tracker bottleneck work COMPLETE (Steps 1–13 committed on branch `v5`). Plan now covers the inference plane build on top of that foundation.

---

## Part 1 — Completed Baseline (Steps 1–13, all committed)

| Commit | What was done |
|--------|---------------|
| `9206a1c` | Stability fields added to `TrackingTrackSnapshot` (`sampled_at`, `age_frames`, `consecutive_hits`, `frames_since_update`, `persistent_id_state`) |
| `2225e74` | `TrackedPerson` stability fields; `_to_supervision_detections` pre-allocates arrays in-place; reads `age`/`hit_streak`/`frames_since_update` from `sv.Detections.data` |
| `b38d6b8` | `transforms.Compose` built once in `__init__`; `torch.inference_mode()` wraps forward loop |
| `b93e472` | `SharedEmbeddingService` — one embedder, `asyncio.Queue` batching, per-request `Future`, `embed_from_thread()` for worker threads |
| `4b03534` | `MilvusIdentityStore.batch_resolve()` — single `client.search()` round-trip; `asyncio.Semaphore(4)` concurrency cap |
| `c2f474c` | ByteTrack defaults tuned for 8 fps CCTV (`lost_buffer=30`, `activation=0.45`, `min_frames=3`, `iou=0.2`) |
| `0adddba` | `DetectorPool` — asyncio.Semaphore checkout, context-manager + manual API |
| `061ab75` | `worker.py` refactor — enrichment thread splits Milvus off hot path; crop size gate (32×64); bounded annotated-stream queue (max 4); stability fields in snapshots |
| `538ce8e` | `TrackingStreamManager` wires `DetectorPool` + `SharedEmbeddingService`; per-camera detector checkout/return |
| `eb78336` | WebSocket broadcast: snapshot → release lock → `asyncio.gather` with 2 s timeout → evict stale |
| `15c2e9d` | `FanoutTrackingUpdatePublisher` uses `asyncio.gather` |
| `17ae5aa` | Bootstrap creates `DetectorPool` and `SharedEmbeddingService`, passes to manager |
| `02310fd` | Stability fields added to Kafka and WebSocket tracking payloads |

### Foundation invariants — do not break these
- `TrackingTrackSnapshot` stability fields are the authoritative tracker contract downstream.
- `SharedEmbeddingService` is the only re-id embedding path. No per-worker embedders.
- `DetectorPool` is the only detector acquisition mechanism. Inference must not touch detector ownership.
- Worker split (decode/detect/track on hot path; identity enrichment off hot path) is the backpressure model.
- Bounded annotated-stream queue and parallel WebSocket/Kafka fanout are the default output model.

---

## Part 2 — Known Codebase Debt to Address Before or During Inference Plane

These issues were found during the audit and must be resolved as part of the inference work.

### D-1: `TrackingWorkerConfig.embedder_name` is dead code
**Location:** `src/services/realtime_video/contracts.py:TrackingWorkerConfig` — field `embedder_name: str = "mobilenet"` is stored but never read after the Step 8 refactor.
**Action:** Remove the field in the first inference-plane commit to avoid false dependencies.

### D-2: `InferenceTrackSnapshot` is orphaned
**Location:** `src/services/realtime_video/contracts.py:134–147` — dataclass `InferenceTrackSnapshot` exists (`track_id`, `persistent_id`, `label`, `confidence`, bbox, `model_name`, `timestamp`) with zero usages in the codebase.
**Action:** Extend or replace it as the canonical inference result contract. Do not introduce a parallel struct. Decision: extend with `strategy`, `alert_level`, `score`, and `sampled_at`; remove the duplicate `timestamp` field.

### D-3: `camera.ai_results` Kafka consumer silently drops payloads
**Location:** `src/services/stream/kafka_event_consumer.py` — subscribes to `camera.ai_results` but deserialises every message as `StreamEventPayload` (a stream lifecycle schema). Inference data is discarded.
**Action:** Add a typed `InferenceKafkaEventPayload` schema and a dedicated handler branch in the consumer. This is the wire-up point for frontend push of inference results.

### D-4: `stream_contract_service.py` needs an inference extension point
**Location:** `src/services/presentation/stream_contract_service.py:StreamContractService.build_contract()` — builds `StreamInfoResponse` from camera + stream + tracking snapshots.
**Action:** Add optional `inference_snapshot: InferenceSnapshot | None = None` parameter. Construct a new `InferenceStateResponse` field in `StreamInfoResponse` when present. This is the only place to add inference to the REST info response.

### D-5: `StreamInfoResponse` and `StreamStartRequest` have no inference fields
**Location:** `src/schemas/stream_responses.py:StreamInfoResponse`, `src/schemas/stream_requests.py:StreamStartRequest`.
**Action:**
- Add `inference: InferenceStateResponse | None = None` to `StreamInfoResponse`.
- Add `enable_inference: bool | None = None` to `StreamStartRequest` (opt-in at stream start, not mandatory).

### D-6: No `PATCH /streams/{camera_id}/inference` endpoint exists
**Location:** `src/routes/stream_routes.py` — only has POST `/start`, `/stop` and GET `/status`, `/info`, WebSocket `/ws/updates`. No PATCH.
**Action:** Add `PATCH /streams/{camera_id}/inference` with body `{ enabled?: bool, strategy?: "cnn_transformer" | "vjepa_probe" }`. Route delegates to `InferenceManager.configure_stream()`.

### D-7: `main.py` lifespan has no InferenceManager hook
**Location:** `src/main.py:ApplicationContainer` — constructed after `create_tracking_runtime_services()`. The lifespan `finally` block tears down services.
**Action:** Initialise `InferenceManager` immediately after `create_tracking_runtime_services()` returns; add it to `ApplicationContainer`; call `await inference_manager.close()` in the `finally` block, before MediaMTX shutdown. Mirror the tracking manager lifecycle exactly.

### D-8: `MetricsRecorder` protocol needs new queue-depth methods
**Location:** `src/observability/metrics.py:MetricsRecorder` protocol and `NullMetricsRecorder`.
**Action:** Add methods for every new queue introduced:
- `observe_detector_pool_wait(camera_id, seconds)`
- `observe_embedding_queue_depth(depth)`
- `observe_enrichment_queue_depth(camera_id, depth)`
- `observe_annotated_frame_queue_depth(camera_id, depth)`
- `observe_inference_ingress_queue_depth(camera_id, depth)`
- `increment_inference_frame_drop(camera_id)`

Both `MetricsRecorder` and `NullMetricsRecorder` must be updated together.

---

## Part 3 — Inference Plane Implementation

### 3.1 New module: `src/services/inference/`

```
src/services/inference/
    __init__.py
    contracts.py            — InferenceIngressSample, InferenceResult, InferenceSnapshot, InferenceWorkerConfig
    manager.py              — InferenceManager (mirrors TrackingStreamManager lifecycle)
    orchestrator.py         — InferenceOrchestrator (per-camera coroutine)
    temporal_buffer.py      — TemporalBufferService (keyed by persistent_id, 16-frame rolling window)
    ingress_scheduler.py    — InferenceIngressScheduler (dispatch gate, quality checks)
    triton_client.py        — TritonInferenceClient (gRPC async, bounded in-flight concurrency)
    batch_builder.py        — BatchBuilder (assembles Triton input tensors)
    decision_engine.py      — DecisionEngine (threshold → alert_level)
    event_repository.py     — InferenceEventRepository (persists non-normal alerts to Postgres)
    bootstrap.py            — create_inference_runtime_services()
```

### 3.2 `InferenceIngressSample` contract

```python
@dataclass(slots=True)
class InferenceIngressSample:
    camera_id: str
    stream_name: str
    local_track_id: str
    persistent_id: str          # must be assigned before queuing
    sampled_at: datetime
    left: int
    top: int
    width: int
    height: int
    crop: np.ndarray
    age_frames: int
    consecutive_hits: int
    frames_since_update: int
    persistent_id_state: str    # only "assigned" samples dispatched
```

### 3.3 Ingress injection point

The correct injection point is the `TrackingUpdatePublisher.publish()` call chain — not raw frames, not WebSocket messages.

Concretely: add `InferenceIngressPublisher` that implements `TrackingUpdatePublisher` protocol and is passed into `FanoutTrackingUpdatePublisher` alongside the existing WebSocket and Kafka publishers. It filters, crops, and enqueues samples for the `InferenceIngressScheduler`.

This reuses the existing enrichment crop without re-cropping or re-serialising the same person twice.

### 3.4 Temporal buffer rules

- Buffer keyed by `persistent_id`.
- 16-frame rolling window.
- Buffer continues across camera changes (same `persistent_id`, different `camera_id`).
- Buffer reset only on: 2-second identity gap, or `persistent_id_state` transition to `"pending"`.
- Do not flush on strategy switch.

### 3.5 Dispatch gate (all conditions must be true)

```
persistent_id_state == "assigned"
len(buffer[persistent_id]) >= 16
consecutive_hits >= 4
frames_since_update == 0
crop width >= 32 and height >= 64
```

### 3.6 Model serving via Triton

- Serve both strategies through Triton: `cnn_transformer`, `vjepa_probe`.
- Use Triton gRPC async client with bounded in-flight concurrency (configurable, default 8 per strategy).
- Dynamic batching configured on the Triton side; `BatchBuilder` assembles input tensors per strategy format.
- Feed Triton from `InferenceIngressScheduler` only — not directly from worker threads.
- Use `MilvusIdentityStore.batch_resolve()` for burst identity resolution only; keep refreshes coalesced and off the hot path.

### 3.7 V-JEPA model architecture
- Encoder + attentive probe pattern. Probe head runs on top of frozen encoder features.
- `BatchBuilder` must handle the probe's expected spatial-temporal input shape separately from `cnn_transformer`.

### 3.8 `InferenceStateResponse` schema (new)

```python
class InferenceStateResponse(BaseModel):
    enabled: bool
    strategy: str | None          # "cnn_transformer" | "vjepa_probe"
    available_strategies: list[str]
    healthy: bool
    last_error_message: str | None
    queue_depth: int
    active_tracks: int
    last_result_at: datetime | None
```

### 3.9 Kafka — `camera.ai_results` payload (new schema)

```python
class InferenceKafkaEventPayload(BaseModel):
    event: str = "inference.updated"
    emitted_at: datetime
    camera_id: str
    stream_name: str
    persistent_id: str
    local_track_id: str
    strategy: str
    score: float
    alert_level: str       # "normal" | "warning" | "alert"
    label: str
    model_name: str
    sampled_at: datetime
```

### 3.10 WebSocket events

Reuse `/streams/ws/updates`. Add two new event types:
- `inference.updated` — per-track inference result, same shape as `InferenceKafkaEventPayload`.
- `inference.alert` — non-normal alert, includes `alert_level`, `persistent_id`, `camera_id`.

Do not add a second WebSocket endpoint.

### 3.11 Persistence

Persist only non-`normal` inference alerts to `inference_events` table. `InferenceEventRepository` wraps the asyncpg pool already present via `db.py`.

---

## Part 4 — Implementation Order (Inference Plane)

Execute in order. Each step = one atomic commit.

**Pre-work (debt cleanup):**
1. `contracts.py` — Remove dead `embedder_name` field from `TrackingWorkerConfig`. Extend `InferenceTrackSnapshot` → becomes the `InferenceResult` contract (add `strategy`, `alert_level`, `score`; rename `timestamp` → `sampled_at`). **(D-1, D-2)**
2. `metrics.py` + `NullMetricsRecorder` — Add queue-depth and drop metric methods. **(D-8)**

**Schema and API layer:**
3. `schemas/inference_events.py` (NEW) — `InferenceKafkaEventPayload`, `InferenceStateResponse`. **(D-3, 3.8, 3.9)**
4. `schemas/stream_responses.py` — Add `inference: InferenceStateResponse | None` to `StreamInfoResponse`. **(D-5)**
5. `schemas/stream_requests.py` — Add `enable_inference: bool | None` to `StreamStartRequest`. **(D-5)**
6. `routes/stream_routes.py` — Add `PATCH /streams/{camera_id}/inference` endpoint. **(D-6)**

**Kafka consumer fix:**
7. `stream/kafka_event_consumer.py` — Add `InferenceKafkaEventPayload` handler branch for `camera.ai_results`. **(D-3)**

**Inference service module:**
8. `services/inference/contracts.py` (NEW) — `InferenceIngressSample`, `InferenceSnapshot`, `InferenceWorkerConfig`.
9. `services/inference/temporal_buffer.py` (NEW) — `TemporalBufferService` with `persistent_id` keying and reset rules.
10. `services/inference/ingress_scheduler.py` (NEW) — `InferenceIngressScheduler` with dispatch gate.
11. `services/inference/batch_builder.py` (NEW) — `BatchBuilder` for `cnn_transformer` and `vjepa_probe` input shapes.
12. `services/inference/triton_client.py` (NEW) — `TritonInferenceClient` gRPC async with bounded in-flight concurrency.
13. `services/inference/decision_engine.py` (NEW) — `DecisionEngine` threshold → `alert_level`.
14. `services/inference/event_repository.py` (NEW) — `InferenceEventRepository` asyncpg wrapper.
15. `services/inference/orchestrator.py` (NEW) — `InferenceOrchestrator` per-camera async coroutine.
16. `services/inference/manager.py` (NEW) — `InferenceManager` lifecycle (start/stop per camera, close).
17. `services/inference/bootstrap.py` (NEW) — `create_inference_runtime_services()`.

**Wiring:**
18. `services/tracking/updates.py` — Add `InferenceIngressPublisher` implementing `TrackingUpdatePublisher`. Wire into `FanoutTrackingUpdatePublisher` in bootstrap. **(3.3)**
19. `services/presentation/stream_contract_service.py` — Add `inference_snapshot` parameter to `build_contract()`; construct `InferenceStateResponse`. **(D-4)**
20. `main.py` — Initialise `InferenceManager` after `create_tracking_runtime_services()`; add to `ApplicationContainer`; tear down in `finally`. **(D-7)**

---

## Part 5 — Test Plan

### Unit tests
- `test_temporal_buffer.py` — 16-frame window, buffer continuation across camera switch, reset on 2 s gap, no flush on strategy switch.
- `test_ingress_scheduler.py` — dispatch gate rejects on each failing condition independently.
- `test_batch_builder.py` — correct tensor shapes for `cnn_transformer` and `vjepa_probe`.
- `test_decision_engine.py` — threshold → `alert_level` mapping for both strategies.
- `test_inference_ingress_publisher.py` — filters unassigned tracks, enqueues only gate-passing samples.
- `test_trackers_supervision_adapter.py` — stability metadata survives the `trackers` + `supervision` adapter round-trip.
- `test_detector_pool.py` — pool checkout, concurrent acquire, release on worker exit.
- `test_shared_embedding_service.py` — batching across workers, transform reuse.
- `test_milvus_batch_resolve.py` — batch search, semaphore limiting.
- `test_websocket_fanout.py` — slow client eviction, concurrent sends.
- `test_tracking_worker_split_loop.py` — enrichment queue drains, tracking continues while Milvus stalls.

### Integration tests
- Tracking remains live while Milvus and Triton are both delayed.
- Inference ingress consumes enriched tracking output correctly end-to-end.
- WebSocket and Kafka publish `inference.updated` and `inference.alert` in parallel.
- `PATCH /streams/{camera_id}/inference` changes the next dispatched model without flushing the temporal buffer.
- Non-normal alert events persist to `inference_events`; frontend state updates correctly.

### Performance / soak tests
- Multi-camera tracking does not serialize on detector or embedder.
- Sampled tracking FPS stays above target with inference enabled.
- All queues remain bounded under sustained multi-camera load.
- Annotated-stream publishing drops frames instead of stalling tracking under backpressure.
- Validate event-loop ownership and thread handoff for `SharedEmbeddingService` and Milvus batching under soak load.
- If soak tests show task buildup, replace per-update `asyncio.create_task(...)` fanout in worker with a bounded outbound publisher queue.

---

## Part 6 — Official Documentation References

| Library | URL |
|---------|-----|
| Roboflow Trackers ByteTrack | https://trackers.roboflow.com/latest/trackers/bytetrack/ |
| Roboflow Trackers docs | https://trackers.roboflow.com/develop/ |
| Roboflow Trackers repo | https://github.com/roboflow/trackers |
| Supervision `Detections` | https://supervision.roboflow.com/latest/detection/core/ |
| Triton client/API | https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/_reference/tritonclient/tritonclient.html |
| Triton client async/cancellation | https://docs.nvidia.com/deeplearning/triton-inference-server/archives/triton-inference-server-2610/user-guide/docs/client/README.html |
| Triton Perf Analyzer | https://docs.nvidia.com/deeplearning/triton-inference-server/archives/triton-inference-server-2560/user-guide/docs/perf_analyzer/README.html |
| Triton Model Analyzer | https://docs.nvidia.com/deeplearning/triton-inference-server/archives/triton-inference-server-2540/user-guide/docs/model_analyzer/docs/README.html |
| PyMilvus `search()` | https://milvus.io/api-reference/pymilvus/v2.6.x/MilvusClient/Vector/search.md |
| PyTorch `inference_mode()` | https://docs.pytorch.org/docs/2.9/generated/torch.autograd.grad_mode.inference_mode.html |
| FastAPI websockets | https://fastapi.tiangolo.com/advanced/websockets/ |
| Starlette websockets | https://www.starlette.io/websockets/ |
| Python `asyncio.Queue` | https://docs.python.org/3/library/asyncio-queue.html |
| PyAV basics | https://pyav.org/docs/stable/cookbook/basics.html |
| OpenCV drawing/resize | https://docs.opencv.org/4.x/d6/d6e/group__imgproc__draw.html |

---

## Assumptions
- Active implementation target is `backend/src/`, not the legacy root `main.py`.
- V-JEPA architecture: encoder + attentive probe. Probe runs on frozen encoder features.
- The completed tracker refactor (Part 1) is the baseline. Do not rework it unless a soak test exposes a concrete regression.
- Inference is opt-in per stream (`enable_inference` at start, or `PATCH` after). Tracking always runs regardless of inference state.
- Only non-`normal` inference events are persisted to the database in v1.
