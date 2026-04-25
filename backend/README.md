# Backend

This backend is a Python 3.10+ realtime video-processing and control system. It runs as a **single FastAPI process** that embeds the OpenCV pipeline directly in its lifespan. A standalone OpenCV worker script (`main.py`) is also available for local development with a cv2 preview window, but it is not required for production.

## 1. What the backend does

- stores camera inventory and state in PostgreSQL
- validates RTSP cameras with `ffprobe` or a PyAV fallback
- runs an embedded OpenCV multi-camera processing pipeline for active cameras
- detects people with YOLO
- tracks them locally with ByteTrack
- extracts ReID embeddings and resolves global identities through Milvus
- draws per-track overlays: bounding box, persistent ID, confidence, and — once Triton results arrive — inference label, score, and alert level
- optionally forwards identity-qualified crops into a Triton-backed behavior inference pipeline
- publishes tracking, frame, identity, and inference events to Kafka
- consumes Kafka events in the same process and rebroadcasts them to WebSocket clients
- exposes health endpoints and Prometheus metrics

## 2. Runtime model

### 2.1 FastAPI control plane with embedded pipeline

Entrypoint: `backend/src/main.py`

This is the only process you need to run in production. On startup it:

1. connects to PostgreSQL and optionally applies migrations
2. starts the shared Kafka producer service
3. creates the inference manager
4. bootstraps an optional env-configured RTSP camera (`OPENCV_PIPELINE_RTSP_URL`)
5. starts `OpenCvPipelineRuntime` as a background asyncio task
6. starts the Kafka-to-WebSocket `StreamEventConsumer`
7. exposes HTTP, WebSocket, and Prometheus endpoints

On shutdown the pipeline, inference manager, Kafka producer, and consumer are all stopped cleanly in the FastAPI lifespan `finally` block.

### 2.2 Standalone OpenCV dev worker (optional)

Entrypoint: `backend/main.py`

A self-contained script for local inspection. It runs the same `OpenCvPipelineRuntime` with the cv2 annotated preview window enabled by default, connects to its own DB and Kafka producer, and accepts CLI flags for RTSP bootstrap, display, and inference strategy. It is **not** the production entry point — it is a development and debugging tool.

## 3. High-level architecture

```mermaid
flowchart LR
    subgraph Cameras
        C1[RTSP Camera A]
        C2[RTSP Camera B]
        CN[RTSP Camera N]
    end

    subgraph Server[FastAPI server - src/main.py]
        subgraph Pipeline[OpenCvPipelineRuntime - background task]
            CAP[VideoCaptureWorker per camera]
            BUF[FrameBuffer]
            SYNC[MultiCameraSynchronizer]
            PIPE[Preprocess + Calibration + Stabilization + Motion + Detection + Tracking + ReID + Identity]
            ANN[FrameAnnotator + InferenceOverlayCache]
            OUT[OutputDispatcher]
            ING[InferenceIngressPublisher]
        end
        REST[REST API]
        WS[WebSocketManager]
        CON[StreamEventConsumer]
        IM[InferenceManager]
        MET[/Prometheus metrics/]
    end

    subgraph Infra[Shared infrastructure]
        PG[(PostgreSQL)]
        K[(Kafka)]
        M[(Milvus)]
        T[Triton Inference Server]
    end

    UI[Frontend / operator clients]

    C1 --> CAP
    C2 --> CAP
    CN --> CAP
    CAP --> BUF --> SYNC --> PIPE --> ANN --> OUT
    PIPE --> M
    OUT --> K
    OUT --> ING --> IM --> T
    IM --> K
    IM --> PG
    IM -.->|result callback| ANN

    PG --> Pipeline
    K --> CON --> WS --> UI
    REST --> UI
    Server --> MET
```

Key characteristics:

- PostgreSQL is the source of truth for camera inventory.
- Kafka is the event backbone from pipeline output to WebSocket clients.
- Milvus is used by the tracking identity layer.
- Triton is used by the inference manager after identity assignment.
- The `InferenceOverlayCache` receives results via a direct callback from the inference orchestrator — no Kafka round-trip — so labels appear on the cv2 window and annotated frame previews immediately.
- One process handles HTTP, WebSocket, pipeline processing, Kafka production, and Kafka consumption.

## 4. Component-level architecture

### 4.1 FastAPI control plane internals

```mermaid
flowchart TD
    APP[FastAPI app]
    CFG[Settings]
    DB[Database asyncpg pool]
    CAMREP[CameraRepository]
    CAMSVC[CameraService]
    VAL[CameraValidator]
    KPROD[TrackingKafkaProducerService]
    IM[InferenceManager]
    WS[WebSocketManager]
    KCON[StreamEventConsumer]
    PIPE[OpenCvPipelineRuntime]
    MET[PrometheusMetrics / collectors]
    ROUTES[Routes: /health /cameras /streams]

    APP --> CFG
    APP --> DB
    APP --> CAMREP --> CAMSVC
    CAMSVC --> VAL
    APP --> KPROD
    APP --> IM
    APP --> PIPE
    APP --> WS
    APP --> KCON --> WS
    APP --> MET
    APP --> ROUTES
```

### 4.2 OpenCV pipeline internals

```mermaid
flowchart TD
    REFRESH[refresh_cameras from PostgreSQL]
    CAP[VideoCaptureWorker per camera]
    FB[FrameBuffer]
    SYNC[MultiCameraSynchronizer]
    PRE[FramePreprocessor - INTER_AREA downscale]
    CAL[CalibrationService]
    STAB[OpticalFlowStabilizer - skips near-identity warps]
    MOT[MotionAnalyzer]
    DET[YOLOBatchDetector]
    TRK[ByteTrackStage]
    REID[BodyReIdentifier]
    ID[IdentityAssignmentService]
    CACHE[InferenceOverlayCache]
    ANN[FrameAnnotator]
    OUT[OutputDispatcher]
    K[(Kafka)]
    MIL[(Milvus)]
    INF[InferenceIngressPublisher -> InferenceManager -> Triton]

    REFRESH --> CAP --> FB --> SYNC --> PRE --> CAL --> STAB --> MOT --> DET --> TRK --> REID --> ID --> ANN --> OUT
    ID --> MIL
    OUT --> K
    OUT --> INF
    INF -.->|result_callback| CACHE
    CACHE --> ANN
```

## 5. Source tree and subsystem ownership

```text
backend/
├── main.py                         # standalone OpenCV dev worker (optional, not production)
├── src/main.py                     # FastAPI + embedded pipeline entrypoint (production)
├── src/core/                       # settings, database, logging, exception wiring
├── src/routes/                     # HTTP and WebSocket routes
├── src/services/
│   ├── camera/                     # camera CRUD, validation, repository access
│   ├── inference/                  # Triton-backed inference pipeline
│   ├── presentation/               # websocket fanout
│   ├── stream/                     # Kafka event consumer for websocket rebroadcast
│   ├── tracking/                   # tracking contracts, ReID embedding, identity store adapters
│   └── tracking_kafka/             # Kafka producer lifecycle and publishers
├── src/opencv_pipeline/            # capture-to-output worker pipeline
├── src/observability/              # metrics, middleware, collectors, metrics server
├── src/models/                     # runtime data models and enums
├── src/schemas/                    # API and event payload schemas
├── scripts/migrations/             # startup-applied SQL migrations
├── scripts/sql/                    # repository SQL files
├── observability/                  # Prometheus, Grafana, Loki, Alloy, Kafka JMX assets
├── docker-compose.yaml             # Milvus, Triton, Kafka, observability stack
├── requirements.txt
└── pyproject.toml
```

## 6. Service breakdown and responsibilities

### 6.1 Core platform services

#### `src/core/config.py`
Single configuration source.

Notable behavior:
- loads `.env` from the backend root
- resolves relative paths against `backend/`
- normalizes comma-separated CORS origins
- parses list-like detection class IDs

#### `src/core/db.py`
Async PostgreSQL wrapper around `asyncpg`.

#### `src/core/logger/logger.py`
Configures rotating file logging with flat output — no process subdirectories or PID suffixes.

Log files written to `LOG_DIRECTORY` (default `runtime/logs/`):

| File | Contents |
| --- | --- |
| `all.log` | every log record (requires `FILE_LOGS_ENABLED=true`) |
| `inference.log` | `src.services.inference.*` + `inference.*` structured events |
| `prediction.log` | final per-track prediction labels, scores, model names, and alert levels (`inference.prediction_*`) |
| `milvus.log` | `src.opencv_pipeline.identity.*` + `src.services.tracking.identity.*` |
| `person_detection.log` | `src.opencv_pipeline.detection.*` + `person_detection.*` structured events |
| `streaming.log` | `src.opencv_pipeline.runtime`, ingestion, output, buffering, preprocessing, motion, stabilization, calibration |
| `tracker.log` | `src.opencv_pipeline.tracking.*` + `src.services.tracking.trackers.*` |
| `body_inference.log` | ReID stage logs |

Subsystem files are written only when `SUBSYSTEM_LOGS_ENABLED=true`. `SUBSYSTEM_LOG_DIRECTORY` is no longer a separate setting — all files land in `LOG_DIRECTORY`.

#### `src/utils/migration_runner.py`
Applies numbered SQL migrations from `scripts/migrations`.

### 6.2 Camera management services

#### `CameraRepository`
Maps SQL files to `CameraRecord` objects. Operations: insert, fetch by id, paginated list, update, delete, update validation status.

#### `CameraService`
Business logic over the repository. Generates camera IDs (`cam_<12 hex chars>`), enforces RTSP source constraint, delegates validation to `CameraValidator`.

#### `CameraValidator`
RTSP validation: `ffprobe` → PyAV fallback → stable machine-readable result codes (`RTSP_REACHABLE`, `RTSP_AUTH_FAILED`, `RTSP_TIMEOUT`, `RTSP_HOST_UNREACHABLE`, `RTSP_UNREACHABLE`).

### 6.3 Kafka services

#### `TrackingKafkaProducerService`
Shared Kafka producer lifecycle wrapper. Degrades to null publishers when Kafka is disabled or unavailable.

#### `StreamEventConsumer`
Subscribes to `camera.tracking.updates`, `camera.ai_results`, `camera.frames`, `identity.events` and rebroadcasts each message to `WebSocketManager`.

### 6.4 Presentation service

#### `WebSocketManager`
Connection registry with concurrent broadcast. Supports optional camera-scoped subscriptions via `camera_id` query param.

### 6.5 Inference services

#### `InferenceManager`
Lifecycle owner for per-camera `InferenceOrchestrator` instances.

New: supports `set_result_callback(fn)` — the pipeline runtime registers a callback here so inference results are fed directly into `InferenceOverlayCache` without a Kafka round-trip.

#### `InferenceIngressPublisher`
Bridge from tracking output into inference input. Crops person patches and pushes `InferenceIngressSample` objects to the manager. Short temporal histories are padded in the batch builder, so Triton inference can start as soon as a person track first appears instead of waiting for a full 16-frame history.

#### `InferenceOrchestrator`
Per-camera async inference loop using the Triton gRPC client. After scoring, calls `result_callback(camera_id, local_track_id, label, score, alert_level)` before dispatching to Kafka and WebSocket, so the cv2 overlay updates immediately.

#### `InferenceEventRepository`
Persists non-normal inference events to PostgreSQL.

> **Known maintenance item:** the checked-in migration `004_create_inference_events_table.sql` defines an older schema; align it with the active repository write shape before relying on inference-event persistence.

### 6.6 OpenCV pipeline stages

The pipeline is wired in `src/opencv_pipeline/runtime.py`.

#### `VideoCaptureWorker` (`ingestion/`)
Owns capture for one camera with exponential-backoff reconnect.

#### `FrameBuffer` (`buffering/`)
Bounded queue shared across cameras with configurable drop policy.

#### `MultiCameraSynchronizer` (`buffering/`)
Groups frames into synchronized bundles; rebuilt dynamically when cameras drop out.

#### `FramePreprocessor` (`preprocessing/`)
Resizes frames using `INTER_AREA` when downscaling (sharper than bilinear for CCTV feeds) and `INTER_LINEAR` when upscaling. Produces BGR, RGB, normalized RGB, and grayscale views.

#### `CalibrationService` (`calibration/`)
Loads optional per-camera calibration profiles, applies undistortion, aligns frames to a world plane, projects tracks to world coordinates.

#### `OpticalFlowStabilizer` (`stabilization/`)
Lucas-Kanade optical flow plus affine estimation. **Skips the warpAffine call entirely when the estimated transform is near-identity** (translation < 0.5 px, rotation < 0.003 rad), eliminating per-frame interpolation blur on static CCTV mounts. When a warp is applied it uses `INTER_CUBIC` for sharper results.

#### `MotionAnalyzer` (`motion/`)
Optical flow and foreground estimation producing `MotionSummary` values.

#### `YOLOBatchDetector` (`detection/`)
Batched person detection using the configured YOLO model.

#### `ByteTrackStage` (`tracking/`)
Per-camera local track continuity using ByteTrack.

#### `BodyReIdentifier` (`reid/`)
Appearance embeddings via `TrackingReIdEmbedder`.

#### `MilvusIdentityStore` + `IdentityAssignmentService`
Resolve local tracks to persistent global identities. Batch upserts are deduplicated by `identity_id` before being sent to Milvus — prevents `MilvusException code=1100` when multiple tracks in one frame batch match the same person. Original `first_seen_ts` is preserved for matched identities via a `client.get()` prefetch.

Lifecycle events emitted: `identity.created`, `identity.updated`, `identity.merged`, `identity.expired`.

#### `InferenceOverlayCache`
Dictionary keyed by `(camera_id, local_track_id)` storing the latest `{label, score, alert_level}` per track. Written by the inference orchestrator callback; read by `FrameAnnotator`. Both happen on the asyncio event loop thread so no locking is needed. Entries are evicted when a camera is removed.

#### `FrameAnnotator`
Draws on each frame:
- green bounding box per track
- persistent ID (or local track ID) and detection confidence above the box
- inference label, score percentage, and alert level below the box (once results arrive from Triton); color-coded: green = normal, yellow = warning, red = alert
- motion summary line at the top-left

#### `OutputDispatcher`
Publishes tracking snapshots, frame previews, and identity lifecycle events to Kafka. Renders the annotated frame to the cv2 window when `OPENCV_PIPELINE_DISPLAY_ENABLED=true`.

## 7. Data model and persistence

### 7.1 PostgreSQL tables

#### `cameras`
Source of truth for registered cameras. Key fields: `id`, `name`, `location`, `host`, `port`, `username`, `password`, `path`, `direct_rtsp_url`, `transport`, `status`, `metadata` JSONB, `tags`, validation timestamps. Constraint: each row must have either `direct_rtsp_url` or both `host` and `path`.

#### `stream_state`
Schema exists; not a first-class API surface in the current control plane.

#### `inference_events`
Exists in migrations; schema is out of sync with `InferenceEventRepository`. Treat as an active maintenance item.

### 7.2 Milvus collection

Stores persistent person identities with embeddings. Configured via settings (URI, collection name, dimension, similarity threshold, search limit, concurrency).

Primary key: `identity_id` (VARCHAR). Batch upserts are deduplicated by this key before each write.

### 7.3 Runtime files

```text
runtime/
├── logs/
│   ├── all.log
│   ├── inference.log
│   ├── prediction.log
│   ├── milvus.log
│   ├── person_detection.log
│   ├── streaming.log
│   ├── tracker.log
│   └── body_inference.log
├── calibration/        optional per-camera calibration JSON
└── milvus/             Milvus data when running via Docker Compose
```

## 8. End-to-end data flow

### 8.1 Camera registration and validation flow

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI
    participant CS as CameraService
    participant CV as CameraValidator
    participant PG as PostgreSQL

    Client->>API: POST /cameras
    API->>CS: create_camera(payload)
    CS->>PG: insert camera row
    PG-->>CS: CameraRecord
    CS-->>API: CameraResponse
    API-->>Client: ApiResponse(success)

    Client->>API: POST /cameras/{id}/validate
    API->>CS: validate_camera(id)
    CS->>CV: validate(camera)
    CV-->>CS: CameraValidationResult
    CS->>PG: update validation status
    API-->>Client: validation response
```

### 8.2 Pipeline processing flow

```mermaid
sequenceDiagram
    participant Cam as RTSP camera
    participant W as VideoCaptureWorker
    participant B as FrameBuffer
    participant S as Synchronizer
    participant P as OpenCV stages
    participant MI as Milvus identity
    participant O as OutputDispatcher
    participant K as Kafka

    Cam->>W: video frames
    W->>B: FramePacket
    B->>S: packet
    S->>P: synchronized bundle
    P->>P: preprocess/calibrate/stabilize/motion/detect/track/reid
    P->>MI: embedding lookup/upsert (deduplicated batch)
    MI-->>P: persistent identity assignments
    P->>O: PipelineOutput with annotated frame
    O->>K: camera.tracking.updates
    O->>K: camera.frames
    O->>K: identity.events
```

### 8.3 Behavior inference flow

```mermaid
sequenceDiagram
    participant Track as Tracking output
    participant Ingress as InferenceIngressPublisher
    participant IM as InferenceManager
    participant IO as InferenceOrchestrator
    participant T as Triton
    participant CB as InferenceOverlayCache
    participant PG as PostgreSQL
    participant K as Kafka
    participant WS as WebSocket clients

    Track->>Ingress: frame + tracks
    Ingress->>IM: InferenceIngressSample per eligible track
    IM->>IO: queued batch
    IO->>T: infer(model_name, tensors)
    T-->>IO: output tensor
    IO->>CB: result_callback(camera_id, track_id, label, score, alert_level)
    Note over CB: next frame render picks up label
    IO->>WS: inference.updated / inference.alert
    IO->>K: camera.ai_results
    IO->>PG: persist non-normal results only
```

### 8.4 API WebSocket bridge flow

```mermaid
sequenceDiagram
    participant Pipeline
    participant Kafka
    participant API as StreamEventConsumer
    participant WM as WebSocketManager
    participant Browser

    Pipeline->>Kafka: tracking/frame/identity/inference events
    Kafka->>API: subscribed topic message
    API->>WM: WebSocketEnvelope
    WM->>Browser: JSON event
```

## 9. Kafka topics and event contracts

### 9.1 Active topics

| Topic | Produced by | Consumed by | Purpose |
| --- | --- | --- | --- |
| `camera.tracking.updates` | `OutputDispatcher` | `StreamEventConsumer` | per-camera track snapshots |
| `camera.frames` | `OutputDispatcher` | `StreamEventConsumer` | frame metadata and optional JPEG preview |
| `identity.events` | `OutputDispatcher` | `StreamEventConsumer` | identity lifecycle events |
| `camera.ai_results` | `InferenceOrchestrator` | `StreamEventConsumer` | inference scores and alert levels |

### 9.2 Reserved topics (not actively used)

`camera.status` and `camera.events` — provisioned in `kafka-init`, no matching producer/consumer in current code.

### 9.3 Payload shapes

#### `camera.tracking.updates` — `TrackingKafkaEventPayload`
`event`, `emitted_at`, `camera_id`, `stream_name`, `annotated_stream_name`, `active_tracks`, `tracks[]` (ids, persistent identity, bbox, score, age, state)

#### `camera.frames` — `CameraFrameKafkaEventPayload`
`camera_id`, `stream_name`, `sequence_number`, `captured_at`, frame dimensions, `pipeline_latency_ms`, motion summary, `detections`, `active_tracks`, optional `preview_jpeg_base64`

#### `identity.events` — `IdentityKafkaEventPayload`
`event`, `occurred_at`, `camera_id`, `stream_name`, `local_track_id`, `persistent_id`, `previous_persistent_id`, `matched_existing`, `similarity`, bbox, optional world coordinates

#### `camera.ai_results` — `InferenceKafkaEventPayload`
`event`, `emitted_at`, `camera_id`, `stream_name`, `persistent_id`, `local_track_id`, `strategy`, `score`, `alert_level`, `label`, `model_name`, `sampled_at`

## 10. API structure and integration points

### 10.1 REST routes

#### Camera routes (`/cameras`)
- `POST /cameras` — create a camera
- `GET /cameras` — paginated list with optional filters
- `GET /cameras/{camera_id}` — fetch one camera
- `PUT /cameras/{camera_id}` — update one camera
- `DELETE /cameras/{camera_id}` — delete camera and remove inference state
- `POST /cameras/{camera_id}/validate` — validate RTSP reachability

#### Health routes (`/health`)
- `GET /health` — aggregated service health (uptime, DB, Kafka producer, Kafka consumer)
- `GET /health/db` — DB-only health check

#### Stream routes (`/streams`)
- `PATCH /streams/{camera_id}/inference` — start, stop, or reconfigure inference
- `GET /streams/health` — Kafka consumer bridge health
- `WS /streams/ws/updates` — realtime WebSocket; optional `camera_id` query param

### 10.2 HTTP response envelope

All REST responses wrapped in `ApiResponse`: `status`, `message`, `data`, optional `error_code`, `timestamp`, optional `meta`.

### 10.3 Error handling

`src/core/exceptions/handler.py`: `AppException` → structured errors, `RequestValidationError` → 422, `Exception` → 500.

## 11. Configuration reference

### 11.1 Required

- `DATABASE_URL`
- `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` when using the provided Milvus compose stack

### 11.2 Application

`APP_NAME`, `APP_VERSION`, `ENVIRONMENT`, `DEBUG`, `PUBLIC_API_BASE_URL`, `PUBLIC_WS_BASE_URL`, `CORS_ORIGINS`

### 11.3 Database

`DATABASE_URL`, `DB_POOL_MIN_SIZE`, `DB_POOL_MAX_SIZE`, `RUN_MIGRATIONS_ON_STARTUP`

### 11.4 Kafka

`KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_GROUP_ID`, `KAFKA_CLIENT_ID`, `KAFKA_ENABLED`, `KAFKA_TOPIC_CAMERA_STATUS`, `KAFKA_TOPIC_CAMERA_EVENTS`, `KAFKA_TOPIC_CAMERA_AI_RESULTS`, `KAFKA_TOPIC_CAMERA_TRACKING_UPDATES`, `KAFKA_TOPIC_CAMERA_FRAMES`, `KAFKA_TOPIC_IDENTITY_EVENTS`

### 11.5 Metrics

`METRICS_ENABLED`, `METRICS_HOST`, `METRICS_PORT`, `METRICS_COLLECTION_INTERVAL_SECONDS`

### 11.6 Inference

`TRITON_URL`, `OPENCV_PIPELINE_ENABLE_BEHAVIOR_INFERENCE`, `OPENCV_PIPELINE_INFERENCE_STRATEGY`

### 11.7 Tracking and identity

`TRACKING_EMBEDDER_NAME`, `TRACKING_EMBEDDER_WEIGHTS_PATH`, `TRACKING_TRACKER_LOST_TRACK_BUFFER`, `TRACKING_TRACKER_ACTIVATION_THRESHOLD`, `TRACKING_TRACKER_MINIMUM_CONSECUTIVE_FRAMES`, `TRACKING_TRACKER_MINIMUM_IOU_THRESHOLD`, `TRACKING_TRACKER_HIGH_CONF_DET_THRESHOLD`, `TRACKING_IDENTITY_STORE_URI`, `TRACKING_IDENTITY_STORE_TOKEN`, `TRACKING_IDENTITY_COLLECTION_NAME`, `TRACKING_IDENTITY_DIMENSION`, `TRACKING_IDENTITY_STORE_TIMEOUT_SECONDS`, `TRACKING_IDENTITY_SIMILARITY_THRESHOLD`, `TRACKING_IDENTITY_SEARCH_LIMIT`, `TRACKING_IDENTITY_MAX_CONCURRENT_BATCHES`, `TRACKING_IDENTITY_SYNC_INTERVAL_SECONDS`, `TRACKING_PUBLISH_UPDATE_INTERVAL_SECONDS`, `TRACKING_STREAM_SUFFIX`

### 11.8 OpenCV pipeline

| Variable | Default | Notes |
| --- | --- | --- |
| `OPENCV_PIPELINE_ENABLED` | `true` | disable to skip pipeline startup |
| `OPENCV_PIPELINE_RTSP_URL` | — | if set, bootstraps a camera on startup |
| `OPENCV_PIPELINE_RTSP_CAMERA_NAME` | `OpenCV Pipeline Camera` | display name for the bootstrapped camera |
| `OPENCV_PIPELINE_TARGET_WIDTH` | `1280` | |
| `OPENCV_PIPELINE_TARGET_HEIGHT` | `720` | |
| `OPENCV_PIPELINE_TARGET_FPS` | `10.0` | |
| `OPENCV_PIPELINE_FRAME_BUFFER_SIZE` | `128` | |
| `OPENCV_PIPELINE_DROP_POLICY` | `drop_oldest` | |
| `OPENCV_PIPELINE_SYNC_TOLERANCE_MS` | `40.0` | |
| `OPENCV_PIPELINE_BATCH_SIZE` | `8` | |
| `OPENCV_PIPELINE_CAPTURE_RETRY_INITIAL_DELAY_SECONDS` | `0.5` | |
| `OPENCV_PIPELINE_CAPTURE_RETRY_MAX_DELAY_SECONDS` | `5.0` | |
| `OPENCV_PIPELINE_PREVIEW_JPEG_QUALITY` | `100` | quality of JPEG previews sent over WebSocket |
| `OPENCV_PIPELINE_PUBLISH_FRAME_PREVIEWS` | `false` | set `true` to include JPEG in frame events |
| `OPENCV_PIPELINE_DISPLAY_ENABLED` | `false` | cv2 window; set `true` in the dev worker |
| `OPENCV_PIPELINE_DISPLAY_WINDOW_PREFIX` | `OpenCV Pipeline` | |
| `OPENCV_PIPELINE_LOW_LIGHT_THRESHOLD` | `40.0` | |
| `OPENCV_PIPELINE_DETECTION_MODEL_PATH` | `yolo26n.pt` | |
| `OPENCV_PIPELINE_DETECTION_CONFIDENCE` | `0.4` | |
| `OPENCV_PIPELINE_DETECTION_CLASS_IDS` | `0` | comma-separated |
| `OPENCV_PIPELINE_IDENTITY_TTL_SECONDS` | `30.0` | |
| `OPENCV_PIPELINE_REFRESH_ALL_CAMERAS_INTERVAL_SECONDS` | `30.0` | |
| `OPENCV_PIPELINE_CALIBRATION_DIRECTORY` | `runtime/calibration` | |

### 11.9 Logging

| Variable | Default | Notes |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | |
| `JSON_LOGS` | `false` | structured JSON output |
| `FILE_LOGS_ENABLED` | `true` | writes `all.log` |
| `LOG_DIRECTORY` | `runtime/logs` | all log files land here flat — no subdirectories |
| `LOG_FILE_PREFIX` | `backend` | unused in filenames now; kept for compatibility |
| `LOG_FILE_MAX_BYTES` | `10485760` | per-file rotation size |
| `LOG_FILE_BACKUP_COUNT` | `5` | |
| `SUBSYSTEM_LOGS_ENABLED` | `true` | writes per-subsystem `.log` files |

`SUBSYSTEM_LOG_DIRECTORY` has been removed. All log files are written to `LOG_DIRECTORY`.

## 12. Dependencies

### 12.1 Python

Core: `fastapi`, `uvicorn[standard]`, `asyncpg`, `aiokafka`, `opencv-python`, `numpy`, `torch`, `torchvision`, `ultralytics`, `trackers`, `supervision`, `pymilvus`, `tritonclient[grpc]`, `prometheus-client`, `psutil`, `pydantic`, `pydantic-settings`, `tenacity`

Dev/test: `pytest-asyncio`

### 12.2 Infrastructure (Docker Compose)

etcd, MinIO, Milvus standalone, Triton Inference Server, Kafka (KRaft), Kafka topic bootstrap, node-exporter, postgres-exporter, Loki, Grafana Alloy, Prometheus, Grafana.

> PostgreSQL is **not** defined in `docker-compose.yaml`. Provide an external instance via `DATABASE_URL`.

## 13. Deployment and execution

### 13.1 Prerequisites

- Python 3.10+
- `uv` or `pip`
- reachable PostgreSQL database
- Docker Compose v2 for shared services
- model assets expected by Triton and the ReID component
- RTSP-reachable cameras for live operation
- optional: `ffprobe` in `PATH` for camera validation; `av` (PyAV) as fallback

### 13.2 Boot shared infrastructure

```bash
docker compose up -d etcd minio milvus kafka kafka-init triton
```

Optional observability:

```bash
docker compose up -d prometheus grafana loki alloy node-exporter postgres-exporter
```

### 13.3 Prepare Python environment

```bash
uv sync
# or
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

### 13.4 Create `.env`

```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/rtsp_camera
CORS_ORIGINS=http://localhost:3000
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
TRITON_URL=localhost:8001
TRACKING_IDENTITY_STORE_URI=http://localhost:19530
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

# Enable JPEG frame previews for the frontend stream view
OPENCV_PIPELINE_PUBLISH_FRAME_PREVIEWS=true

# Optional: bootstrap one RTSP camera on startup
# OPENCV_PIPELINE_RTSP_URL=rtsp://user:pass@192.168.1.100:554/stream
# OPENCV_PIPELINE_RTSP_CAMERA_NAME=Front Gate
```

> The default `TRACKING_IDENTITY_STORE_URI` points to a local file under `runtime/milvus_tracking.db`. Override it to `http://localhost:19530` to use the Docker Compose Milvus service.

### 13.5 Apply database migrations

Migrations run automatically when `RUN_MIGRATIONS_ON_STARTUP=true` (default). To apply manually:

```bash
uv run python -m src.utils.migration_runner
```

### 13.6 Run the production server

```bash
# development (with reload)
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# production
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000
```

The FastAPI process starts the OpenCV pipeline automatically as a background task. No second process is needed.

### 13.7 Run the standalone dev worker (optional)

```bash
uv run python main.py
# or with an explicit camera
uv run python main.py --rtsp-url "rtsp://user:pass@host:554/stream" --camera-name "Front Gate"
```

This script opens a cv2 preview window with all overlays (bounding boxes, persistent IDs, confidence, and inference labels) and is useful for visually verifying the pipeline without running the full API stack.

> If you run both the FastAPI server and the dev worker on the same host with metrics enabled, set different `METRICS_PORT` values — both default to `9109`.

### 13.8 Access points

| Service | Address |
| --- | --- |
| API | `http://localhost:8000` |
| API docs | `http://localhost:8000/docs` |
| Prometheus metrics | `http://localhost:9109/metrics` |
| Triton gRPC | `localhost:9001` |
| Triton metrics | `http://localhost:8002/metrics` |
| Kafka | `localhost:9092` |
| Milvus | `localhost:19530` |
| Milvus health | `http://localhost:9091/healthz` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3001` |

> Triton HTTP and the API both default to port `8000`. Change one binding before running both on the same host.

## 14. Observability

### 14.1 Application metrics

- frames received, dropped, and processing latency
- queue depth and active tracks
- WebSocket connections and send counts
- Kafka publish/consume success and failure
- dependency health (Milvus, Kafka)
- inference ingress backpressure
- system CPU, memory, and network usage

### 14.2 Metrics collectors

- `SystemMetricsCollector` — psutil-based host/process metrics and pipeline queue depth
- `RuntimeMetricsCollector` — health snapshots from long-lived services
- `HttpMetricsMiddleware` — per-route request counts and latency histograms

### 14.3 Logging

All log files land flat in `LOG_DIRECTORY` with no subdirectories or PID suffixes:

- `all.log` — complete log stream
- `inference.log` — inference subsystem
- `prediction.log` — final per-track prediction labels, scores, model names, and alert levels
- `milvus.log` — Milvus identity store
- `person_detection.log` — YOLO detection stage
- `streaming.log` — capture, buffering, preprocessing, stabilization, output
- `tracker.log` — ByteTrack stage
- `body_inference.log` — ReID stage

### 14.4 Dashboard assets

`observability/prometheus/`, `observability/grafana/`, `observability/loki/`, `observability/alloy/`, `observability/kafka_jmx/`

Local Grafana is provisioned automatically:

- URL: `http://localhost:3001`
- default login: `admin` / `admin`
- dashboard folder: `Pipeline Backend`

## 15. Maintenance notes

### 15.1 Adding new Kafka event types

Update: producer code + `src/schemas/`, topic name in `Settings`, `docker-compose.yaml` `kafka-init`, `StreamEventConsumer` subscription list, frontend WebSocket consumers.

### 15.2 Adding a new pipeline stage

Changes belong in: `src/opencv_pipeline/runtime.py` (orchestration), a new submodule under `src/opencv_pipeline/`, `src/opencv_pipeline/contracts.py` (shared data), `OutputDispatcher` or metrics (external state).

### 15.3 Adding a new inference strategy

Update: `InferenceWorkerConfig`, `BatchBuilder`, Triton model deployment, `DecisionEngine`, `PATCH /streams/{camera_id}/inference` accepted strategy values.

### 15.4 Adding a new persistence model

Pattern: numbered SQL migration → parameterized SQL under `scripts/sql/` → repository methods → keep schema and repository aligned. The current `inference_events` area is an example of what happens when they drift.

## 16. Known implementation realities

1. The system now runs as a single process — FastAPI embeds the OpenCV pipeline. The two-process split described in earlier versions is no longer the default.
2. PostgreSQL is required but not containerized by the provided compose file.
3. `stream_state` schema exists; the exposed API surface is focused on camera CRUD, health, and inference toggling.
4. `camera.status` and `camera.events` are provisioned Kafka topics but are not actively used.
5. The inference-event migration schema does not match the active repository write shape and should be reconciled.
6. Triton HTTP and the FastAPI server both default to port `8000` — plan ports explicitly for local deployment.

## 17. Quick start checklist

1. start PostgreSQL externally and set `DATABASE_URL`
2. start Kafka, Milvus, and Triton from `docker-compose.yaml`
3. install Python dependencies
4. create `.env` (set `OPENCV_PIPELINE_PUBLISH_FRAME_PREVIEWS=true` for frontend stream view)
5. run migrations (automatic with default settings)
6. start the server: `uv run uvicorn src.main:app --host 0.0.0.0 --port 8000`
7. register cameras through `POST /cameras` with `status: active`
8. watch events on `WS /streams/ws/updates`

For visual pipeline inspection without a frontend: `uv run python main.py --rtsp-url "rtsp://..."` — opens a cv2 window with all overlays including inference labels.

## 18. Related code references

| File | Purpose |
| --- | --- |
| `src/main.py` | API + pipeline lifecycle wiring |
| `main.py` | standalone dev worker entrypoint |
| `src/core/config.py` | full configuration surface |
| `src/opencv_pipeline/runtime.py` | pipeline orchestration |
| `src/opencv_pipeline/output/publisher.py` | frame annotation + event emission + inference overlay cache |
| `src/services/inference/manager.py` | inference lifecycle + result callback wiring |
| `src/services/inference/orchestrator.py` | Triton execution and result delivery |
| `src/services/tracking/identity/milvus_store.py` | identity resolution with deduplication |
| `src/services/stream/kafka_event_consumer.py` | Kafka to WebSocket bridge |
| `src/services/camera/camera_service.py` | camera business logic |
| `src/core/logger/logger.py` | flat rotating file log configuration |
