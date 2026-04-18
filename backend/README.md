# Backend

This backend is a Python 3.10+ realtime video-processing and control system split into two executable runtimes:

1. FastAPI control plane (`src/main.py`), which exposes REST and WebSocket interfaces, manages cameras, validates RTSP sources, connects to PostgreSQL, and bridges Kafka events to browser clients.
2. OpenCV edge worker (`main.py`), which continuously reads active cameras from PostgreSQL, runs the OpenCV tracking pipeline, resolves identities with Milvus, optionally forwards crops into Triton-backed behavior inference, and publishes structured events to Kafka.

The implementation is not a generic microservice mesh; it is a tightly-coupled event-driven backend with shared configuration, shared schema definitions, and shared infrastructure dependencies.

This document describes the system as it exists in the current codebase.

## 1. What the backend does

At a high level, the backend:

- stores camera inventory and state in PostgreSQL
- validates RTSP cameras with `ffprobe` or a PyAV fallback when PyAV is separately installed
- runs an OpenCV-based multi-camera processing pipeline for active cameras
- detects people with YOLO
- tracks them locally with ByteTrack
- extracts ReID embeddings and resolves global identities through Milvus
- optionally forwards identity-qualified crops into a Triton-backed behavior inference pipeline
- publishes tracking, frame, identity, and inference events to Kafka
- consumes Kafka events in the API process and rebroadcasts them to WebSocket clients
- exposes health endpoints for the API runtime and Prometheus metrics for both the API and worker runtimes

## 2. Runtime model

There are two main Python processes in this repository.

### 2.1 FastAPI control plane

Entrypoint:
- `backend/src/main.py`

Responsibilities:
- build the FastAPI app
- connect to PostgreSQL
- optionally apply SQL migrations on startup
- construct camera CRUD services
- construct the shared Kafka producer service
- construct the inference manager
- start the Kafka-to-WebSocket `StreamEventConsumer`
- expose HTTP endpoints and the realtime WebSocket endpoint
- expose Prometheus metrics and health endpoints

### 2.2 OpenCV edge worker

Entrypoint:
- `backend/main.py`

Responsibilities:
- connect to PostgreSQL
- optionally apply SQL migrations on startup
- start the shared Kafka producer service
- construct the inference manager for crop-based behavior inference
- load active cameras from PostgreSQL
- spawn one capture worker per active camera
- run the full OpenCV processing pipeline
- publish tracking, frame, identity, and inference events
- expose Prometheus metrics for the worker process

## 3. High-level architecture

```mermaid
flowchart LR
    subgraph Cameras
        C1[RTSP Camera A]
        C2[RTSP Camera B]
        CN[RTSP Camera N]
    end

    subgraph Worker[OpenCV edge worker - backend/main.py]
        CAP[VideoCaptureWorker per camera]
        BUF[FrameBuffer]
        SYNC[MultiCameraSynchronizer]
        PIPE[Preprocess + Calibration + Stabilization + Motion + Detection + Tracking + ReID + Identity]
        OUT[OutputDispatcher]
        ING[InferenceIngressPublisher]
    end

    subgraph Infra[Shared infrastructure]
        PG[(PostgreSQL)]
        K[(Kafka)]
        M[(Milvus)]
        T[Triton Inference Server]
        MET1[/Prometheus metrics/]
    end

    subgraph API[FastAPI control plane - src/main.py]
        REST[REST API]
        WS[WebSocketManager]
        CON[StreamEventConsumer]
        IM[InferenceManager]
        MET2[/Prometheus metrics/]
    end

    UI[Frontend / operator clients]

    C1 --> CAP
    C2 --> CAP
    CN --> CAP
    CAP --> BUF --> SYNC --> PIPE --> OUT
    PIPE --> M
    OUT --> K
    OUT --> ING --> IM --> T
    IM --> K
    IM --> PG

    PG --> API
    PG --> Worker
    K --> CON --> WS --> UI
    REST --> UI
    API --> MET2
    Worker --> MET1
```

Important characteristics of the current implementation:

- PostgreSQL is the source of truth for camera inventory.
- Kafka is the event backbone between the worker and the API process.
- Milvus is used by the tracking identity layer, not by the FastAPI layer directly.
- Triton is used by the inference manager after tracking/identity assignment, not by the YOLO detector inside the OpenCV pipeline.
- The API process and the worker both create an `InferenceManager`, but only the worker naturally feeds it with tracking crops during normal pipeline execution.
- The API exposes `PATCH /streams/{camera_id}/inference`, but that route currently affects the API process's local `InferenceManager` instance only; the worker still auto-configures inference during camera refresh based on worker settings.

## 4. Component-level architecture

### 4.1 Control plane internals

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
    MET[PrometheusMetrics / collectors]
    ROUTES[Routes: /health /cameras /streams]

    APP --> CFG
    APP --> DB
    APP --> CAMREP --> CAMSVC
    CAMSVC --> VAL
    APP --> KPROD
    APP --> IM
    APP --> WS
    APP --> KCON --> WS
    APP --> MET
    APP --> ROUTES
```

### 4.2 OpenCV worker internals

```mermaid
flowchart TD
    REFRESH[refresh_cameras from PostgreSQL]
    CAP[VideoCaptureWorker per camera]
    FB[FrameBuffer]
    SYNC[MultiCameraSynchronizer]
    PRE[FramePreprocessor]
    CAL[CalibrationService]
    STAB[OpticalFlowStabilizer]
    MOT[MotionAnalyzer]
    DET[YOLOBatchDetector]
    TRK[ByteTrackStage]
    REID[BodyReIdentifier]
    ID[IdentityAssignmentService]
    ANN[FrameAnnotator]
    OUT[OutputDispatcher]
    K[(Kafka)]
    MIL[(Milvus)]
    INF[InferenceIngressPublisher -> InferenceManager -> Triton]

    REFRESH --> CAP --> FB --> SYNC --> PRE --> CAL --> STAB --> MOT --> DET --> TRK --> REID --> ID --> ANN --> OUT
    ID --> MIL
    OUT --> K
    OUT --> INF
```

## 5. Source tree and subsystem ownership

```text
backend/
├── main.py                         # OpenCV worker entrypoint
├── src/main.py                     # FastAPI app entrypoint
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
Single configuration source for both runtimes.

Notable behavior:
- loads `.env` from the backend root
- resolves relative paths against `backend/`
- normalizes comma-separated CORS origins
- parses list-like detection class IDs
- exposes migration and SQL directories used by the database layer

#### `src/core/db.py`
Async PostgreSQL wrapper around `asyncpg`.

Responsibilities:
- create pooled connections
- register JSON/JSONB codecs
- load SQL from `scripts/sql`
- expose `fetch`, `fetchrow`, `fetchval`, and `execute` helpers
- provide a simple `ping()` used by health endpoints

#### `src/utils/migration_runner.py`
Applies numbered SQL migrations from `scripts/migrations` and records them in `schema_migrations`.

### 6.2 Camera management services

#### `CameraRepository`
Maps SQL files to `CameraRecord` objects.

Current operations:
- insert camera
- fetch by id
- list paginated cameras with total count
- update camera
- delete camera
- update validation status

#### `CameraService`
Business logic over the repository.

Responsibilities:
- generate camera ids (`cam_<12 hex chars>`)
- merge update payloads with persisted records
- enforce that a camera has either `direct_rtsp_url` or `host + path`
- convert models into API-friendly `CameraResponse`
- validate camera reachability through `CameraValidator`
- expose `list_all_camera_records()` for the worker refresh loop

#### `CameraValidator`
RTSP validation implementation.

Validation path:
1. build RTSP URL from camera fields
2. try `ffprobe`
3. if `ffprobe` is unavailable or not executable, fall back to PyAV when `av` is installed in the runtime environment
4. map known errors into stable machine-readable codes such as:
   - `RTSP_REACHABLE`
   - `RTSP_AUTH_FAILED`
   - `RTSP_TIMEOUT`
   - `RTSP_HOST_UNREACHABLE`
   - `RTSP_UNREACHABLE`
5. persist last validation status and message back to PostgreSQL through `CameraService`

### 6.3 Kafka services

#### `TrackingKafkaProducerService`
Shared Kafka producer lifecycle wrapper.

Responsibilities:
- start a single idempotent `AIOKafkaProducer`
- publish tracking updates through `KafkaTrackingUpdatePublisher`
- create generic JSON publishers for frame, identity, and inference topics
- surface producer health through `health_snapshot()`

Important implementation detail:
- when Kafka is disabled or unavailable, the producer service degrades to null publishers instead of crashing the whole runtime.

#### `StreamEventConsumer`
FastAPI-side Kafka consumer.

Responsibilities:
- subscribe to:
  - `camera.tracking.updates`
  - `camera.ai_results`
  - `camera.frames`
  - `identity.events`
- deserialize JSON payloads
- wrap each message in a `WebSocketEnvelope`
- rebroadcast it via `WebSocketManager`
- report health and failure counts through metrics

### 6.4 Presentation service

#### `WebSocketManager`
Connection registry plus broadcast fanout.

Notable behavior:
- supports optional camera-scoped subscriptions through `camera_id` query param
- snapshots active sockets under a lock, then broadcasts concurrently outside the lock
- removes stale connections after failures
- records websocket connection and send metrics

### 6.5 Inference services

The inference subsystem is assembled in `src/services/inference/bootstrap.py` and coordinated by `InferenceManager`.

#### `InferenceManager`
Top-level lifecycle owner for per-camera `InferenceOrchestrator` instances.

Responsibilities:
- lazily start orchestrators when inference is enabled for a camera
- route crop samples into the correct camera scheduler
- support runtime reconfiguration of inference strategy
- stop and remove per-camera inference state

#### `InferenceIngressPublisher`
Bridge from tracking output into inference input.

Responsibilities:
- receive the current frame and track snapshots
- skip tracks without a persistent identity
- crop person patches from the frame
- create `InferenceIngressSample` values
- push samples into `InferenceManager.ingest_sample()`

#### `InferenceIngressScheduler`
Not fully described here line-by-line, but it is the queueing and dispatch gate between ingress and the orchestrator. It enforces queue limits and quality thresholds before a crop reaches Triton.

#### `InferenceOrchestrator`
Per-camera asynchronous inference loop.

Responsibilities:
- dequeue batches from the scheduler
- build model tensors with `BatchBuilder`
- call Triton through `TritonInferenceClient`
- convert output tensors into scalar scores
- classify scores with `DecisionEngine`
- broadcast results to WebSocket clients
- publish results to Kafka (`camera.ai_results`)
- persist only non-normal results through `InferenceEventRepository`
- maintain health and snapshot state for the camera

#### `InferenceEventRepository`
Persists non-normal inference events to PostgreSQL.

Important implementation note:
- the repository currently writes columns such as `stream_name`, `local_track_id`, `strategy`, `score`, `alert_level`, and `sampled_at`
- the checked-in migration `004_create_inference_events_table.sql` still defines an older schema with fields such as `track_id`, `confidence`, bounding box columns, and `created_at`
- maintainers should align the migration/schema with the repository before relying on inference-event persistence in a fresh environment

### 6.6 OpenCV pipeline stages

The worker runtime in `src/opencv_pipeline/runtime.py` wires the following stages.

#### `VideoCaptureWorker` (`ingestion/`)
- owns capture for one camera
- reconnects with exponential backoff
- emits `FramePacket` objects into the shared frame buffer

#### `FrameBuffer` (`buffering/`)
- bounded queue shared across cameras
- supports configured drop policy (`drop_oldest`, `drop_newest`, `block`)
- exposes queue depth for observability
- can discard buffered frames for removed cameras

#### `MultiCameraSynchronizer` (`buffering/`)
- groups frames from healthy cameras into synchronized bundles
- uses monotonic timestamps and a configurable tolerance window
- is rebuilt dynamically when cameras drop out or recover so a dead camera does not stall the whole bundle pipeline

#### `FramePreprocessor` (`preprocessing/`)
- resizes frames to the configured worker resolution
- prepares BGR, RGB, normalized RGB, and grayscale views
- detects low-light conditions
- refreshes processed-frame state after calibration/stabilization updates

#### `CalibrationService` (`calibration/`)
- loads optional per-camera calibration profiles from `runtime/calibration/<camera_id>.json`
- applies undistortion
- optionally aligns frames to a world plane with homography
- supports image-to-world point projection used to enrich track locations

#### `OpticalFlowStabilizer` (`stabilization/`)
- performs per-camera stabilization using Lucas-Kanade optical flow plus affine estimation

#### `MotionAnalyzer` (`motion/`)
- computes motion descriptors using optical flow and foreground estimation
- produces `MotionSummary` values embedded in frame events and overlays

#### `YOLOBatchDetector` (`detection/`)
- runs batched person detection using the model pointed to by `OPENCV_PIPELINE_DETECTION_MODEL_PATH`
- currently defaults to class id `0` (person)

#### `ByteTrackStage` (`tracking/`)
- maintains per-camera local track continuity
- consumes detector output and produces `TrackedObject` instances

#### `BodyReIdentifier` (`reid/`)
- extracts appearance embeddings for active tracks using `TrackingReIdEmbedder`

#### `MilvusIdentityStore` + `IdentityAssignmentService` (`identity/` + `services/tracking/identity/`)
- resolve local tracks to persistent global identities in a shared Milvus collection
- emit identity lifecycle events:
  - `identity.created`
  - `identity.updated`
  - `identity.merged`
  - `identity.expired`
- expire inactive identities after the configured TTL

#### `FrameAnnotator`
- draws boxes, ids, confidence values, and motion summary text on the frame

#### `OutputDispatcher`
Final publication layer for a processed frame.

Responsibilities:
- publish tracking snapshots to `camera.tracking.updates`
- optionally publish annotated frame previews to `camera.frames`
- publish identity lifecycle events to `identity.events`
- send track/frame data into `InferenceIngressPublisher` when behavior inference is enabled

## 7. Data model and persistence

### 7.1 PostgreSQL tables

Current migrations define at least the following tables.

#### `cameras`
Source of truth for registered cameras.

Key fields:
- `id`
- `name`
- `location`
- `host`, `port`, `username`, `password`, `path`
- `direct_rtsp_url`
- `transport`
- `status`
- `metadata` JSONB
- `tags` text[]
- `last_validated_at`
- `last_validation_status`
- `last_validation_message`
- timestamps

Important constraint:
- each row must have either `direct_rtsp_url` or both `host` and `path`

#### `stream_state`
Tracks stream/runtime state, but it is not currently a first-class active subsystem in the current Python control plane. The schema exists and models are present, but the main FastAPI routes in this backend do not currently expose stream-state CRUD.

#### `inference_events`
Exists in migrations, but the schema currently appears out of sync with `InferenceEventRepository`. Treat this area as an active maintenance item.

### 7.2 Milvus collection

Configured through settings:
- URI or endpoint/token
- collection name
- embedding dimension
- similarity threshold
- search limit
- concurrency limits

Purpose:
- persistent global identity resolution for person ReID across frames and cameras

### 7.3 Runtime files

Used paths include:
- `runtime/logs/` for rotating file logs
- `runtime/logs/subsystems/` for dedicated rotating subsystem logs such as inference, person detection, tracker, body inference, Milvus identity, and streaming
- `runtime/calibration/` for optional camera calibration JSON
- `runtime/milvus/` when running Milvus-related services in Docker Compose

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

### 8.2 Worker processing flow

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
    P->>MI: embedding lookup/upsert
    MI-->>P: persistent identity assignments
    P->>O: PipelineOutput
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
    participant PG as PostgreSQL
    participant K as Kafka
    participant WS as WebSocket clients

    Track->>Ingress: frame + tracks
    Ingress->>IM: InferenceIngressSample per eligible track
    IM->>IO: queued batch
    IO->>T: infer(model_name, tensors)
    T-->>IO: output tensor
    IO->>WS: inference.updated / inference.alert
    IO->>K: camera.ai_results
    IO->>PG: persist non-normal results only
```

### 8.4 API websocket bridge flow

```mermaid
sequenceDiagram
    participant Worker
    participant Kafka
    participant API as StreamEventConsumer
    participant WM as WebSocketManager
    participant Browser

    Worker->>Kafka: tracking/frame/identity/inference events
    Kafka->>API: subscribed topic message
    API->>WM: WebSocketEnvelope
    WM->>Browser: JSON event
```

## 9. Kafka topics and event contracts

### 9.1 Topics actively used by the current Python code

| Topic | Produced by | Consumed by | Purpose |
| --- | --- | --- | --- |
| `camera.tracking.updates` | `OutputDispatcher` via `TrackingKafkaProducerService` | `StreamEventConsumer` | per-camera track snapshots |
| `camera.frames` | `OutputDispatcher` | `StreamEventConsumer` | frame-level metadata, optional preview JPEG |
| `identity.events` | `OutputDispatcher` | `StreamEventConsumer` | identity lifecycle events |
| `camera.ai_results` | `InferenceOrchestrator` | `StreamEventConsumer` | inference scores and alert levels |

### 9.2 Topics prepared in config/compose but not materially used in the current Python implementation

These topics are created by `kafka-init` and present in settings, but this repository does not currently contain a matching end-to-end producer/consumer flow for them:

- `camera.status`
- `camera.events`

They should be treated as reserved or future-use topics unless more code is added.

### 9.3 Payload shapes

#### `camera.tracking.updates`
Defined by `TrackingKafkaEventPayload`.

Fields include:
- `event`
- `emitted_at`
- `camera_id`
- `stream_name`
- `annotated_stream_name`
- `active_tracks`
- `tracks[]` with ids, persistent identity, bbox, score, age, and state

#### `camera.frames`
Defined by `CameraFrameKafkaEventPayload`.

Fields include:
- `camera_id`
- `stream_name`
- `sequence_number`
- `captured_at`
- frame dimensions
- `pipeline_latency_ms`
- motion summary
- `detections`
- `active_tracks`
- optional `preview_jpeg_base64`

#### `identity.events`
Defined by `IdentityKafkaEventPayload`.

Fields include:
- `event`
- `occurred_at`
- `camera_id`
- `stream_name`
- `local_track_id`
- `persistent_id`
- `previous_persistent_id`
- `matched_existing`
- `similarity`
- bbox
- optional world coordinates

#### `camera.ai_results`
Defined by `InferenceKafkaEventPayload`.

Fields include:
- `event`
- `emitted_at`
- `camera_id`
- `stream_name`
- `persistent_id`
- `local_track_id`
- `strategy`
- `score`
- `alert_level`
- `label`
- `model_name`
- `sampled_at`

## 10. API structure and integration points

### 10.1 REST routes

#### Camera routes (`/cameras`)

- `POST /cameras`
  - create a camera row
- `GET /cameras`
  - paginated camera listing with optional filtering
- `GET /cameras/{camera_id}`
  - fetch one camera
- `PUT /cameras/{camera_id}`
  - update one camera
- `DELETE /cameras/{camera_id}`
  - delete one camera and remove associated inference state if present
- `POST /cameras/{camera_id}/validate`
  - validate RTSP reachability

#### Health routes (`/health`)

- `GET /health`
  - aggregated service health, uptime, DB, Kafka producer, Kafka consumer
- `GET /health/db`
  - DB-only health check

#### Stream routes (`/streams`)

- `PATCH /streams/{camera_id}/inference`
  - start, stop, or reconfigure inference for the API process's local inference manager state for a camera
- `GET /streams/health`
  - health of the Kafka stream event consumer bridge
- `WS /streams/ws/updates`
  - realtime websocket stream for Kafka-backed events
  - optional query parameter: `camera_id`

### 10.2 HTTP response envelope

All REST responses are wrapped in `ApiResponse`:

- `status`: `success` or `error`
- `message`
- `data`
- `error_code` for failures
- `timestamp`
- optional `meta`

### 10.3 Error handling

`src/core/exceptions/handler.py` registers three layers:
- `AppException` -> structured application errors
- `RequestValidationError` -> 422 with validation details
- generic `Exception` -> 500 with `INTERNAL_SERVER_ERROR`

### 10.4 External integration points

The backend integrates with:
- PostgreSQL through `asyncpg`
- Kafka through `aiokafka`
- Milvus through `pymilvus`
- Triton through `tritonclient[grpc]`
- RTSP validation through `ffprobe`, with a PyAV fallback only when `av`/PyAV is installed in the runtime environment
- Prometheus through `prometheus_client`

## 11. Configuration reference

Configuration is declared in `src/core/config.py` and loaded from environment variables / `.env`.

### 11.1 Required configuration

At minimum, a working environment needs:

- `DATABASE_URL`
- `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` if running the provided Milvus compose stack
- optionally `TRACKING_DETECTOR_API_KEY` depending on the detector/backend actually used by the installed tracking stack

### 11.2 Main application settings

- `APP_NAME`
- `APP_VERSION`
- `ENVIRONMENT`
- `DEBUG`
- `PUBLIC_API_BASE_URL`
- `PUBLIC_WS_BASE_URL`
- `CORS_ORIGINS`

### 11.3 Database settings

- `DATABASE_URL`
- `DB_POOL_MIN_SIZE`
- `DB_POOL_MAX_SIZE`
- `RUN_MIGRATIONS_ON_STARTUP`

### 11.4 Kafka settings

- `KAFKA_BOOTSTRAP_SERVERS`
- `KAFKA_GROUP_ID`
- `KAFKA_CLIENT_ID`
- `KAFKA_ENABLED`
- `KAFKA_TOPIC_CAMERA_STATUS`
- `KAFKA_TOPIC_CAMERA_EVENTS`
- `KAFKA_TOPIC_CAMERA_AI_RESULTS`
- `KAFKA_TOPIC_CAMERA_TRACKING_UPDATES`
- `KAFKA_TOPIC_CAMERA_FRAMES`
- `KAFKA_TOPIC_IDENTITY_EVENTS`

### 11.5 Metrics settings

- `METRICS_ENABLED`
- `METRICS_HOST`
- `METRICS_PORT`
- `METRICS_COLLECTION_INTERVAL_SECONDS`

### 11.6 Inference settings

- `TRITON_URL`
- `OPENCV_PIPELINE_ENABLE_BEHAVIOR_INFERENCE`
- `OPENCV_PIPELINE_INFERENCE_STRATEGY`

### 11.7 Tracking and identity settings

- `TRACKING_ENABLED_BY_DEFAULT`
- `TRACKING_SAMPLE_FPS`
- `TRACKING_OUTPUT_FPS`
- `TRACKING_DETECTOR_MODEL_ID`
- `TRACKING_DETECTOR_CONFIDENCE_THRESHOLD`
- `TRACKING_DETECTOR_IOU_THRESHOLD`
- `TRACKING_DETECTOR_TARGET_CLASS_NAME`
- `TRACKING_DETECTOR_API_KEY`
- `TRACKING_EMBEDDER_NAME`
- `TRACKING_EMBEDDER_WEIGHTS_PATH`
- `TRACKING_TRACKER_LOST_TRACK_BUFFER`
- `TRACKING_TRACKER_ACTIVATION_THRESHOLD`
- `TRACKING_TRACKER_MINIMUM_CONSECUTIVE_FRAMES`
- `TRACKING_TRACKER_MINIMUM_IOU_THRESHOLD`
- `TRACKING_TRACKER_HIGH_CONF_DET_THRESHOLD`
- `TRACKING_IDENTITY_STORE_URI`
- `TRACKING_IDENTITY_STORE_TOKEN`
- `TRACKING_IDENTITY_COLLECTION_NAME`
- `TRACKING_IDENTITY_DIMENSION`
- `TRACKING_IDENTITY_STORE_TIMEOUT_SECONDS`
- `TRACKING_IDENTITY_SIMILARITY_THRESHOLD`
- `TRACKING_IDENTITY_SEARCH_LIMIT`
- `TRACKING_IDENTITY_MAX_CONCURRENT_BATCHES`
- `TRACKING_IDENTITY_SYNC_INTERVAL_SECONDS`
- `TRACKING_PUBLISH_UPDATE_INTERVAL_SECONDS`
- `TRACKING_STREAM_SUFFIX`

### 11.8 OpenCV pipeline settings

- `OPENCV_PIPELINE_ENABLED`
- `OPENCV_PIPELINE_TARGET_WIDTH`
- `OPENCV_PIPELINE_TARGET_HEIGHT`
- `OPENCV_PIPELINE_TARGET_FPS`
- `OPENCV_PIPELINE_FRAME_BUFFER_SIZE`
- `OPENCV_PIPELINE_DROP_POLICY`
- `OPENCV_PIPELINE_SYNC_TOLERANCE_MS`
- `OPENCV_PIPELINE_BATCH_SIZE`
- `OPENCV_PIPELINE_CAPTURE_RETRY_INITIAL_DELAY_SECONDS`
- `OPENCV_PIPELINE_CAPTURE_RETRY_MAX_DELAY_SECONDS`
- `OPENCV_PIPELINE_PREVIEW_JPEG_QUALITY`
- `OPENCV_PIPELINE_PUBLISH_FRAME_PREVIEWS`
- `OPENCV_PIPELINE_LOW_LIGHT_THRESHOLD`
- `OPENCV_PIPELINE_DETECTION_MODEL_PATH`
- `OPENCV_PIPELINE_DETECTION_CONFIDENCE`
- `OPENCV_PIPELINE_DETECTION_CLASS_IDS`
- `OPENCV_PIPELINE_IDENTITY_TTL_SECONDS`
- `OPENCV_PIPELINE_REFRESH_ALL_CAMERAS_INTERVAL_SECONDS`
- `OPENCV_PIPELINE_CALIBRATION_DIRECTORY`

### 11.9 Logging settings

- `LOG_LEVEL`
- `JSON_LOGS`
- `FILE_LOGS_ENABLED`
- `LOG_DIRECTORY`
- `LOG_FILE_PREFIX`
- `LOG_FILE_MAX_BYTES`
- `LOG_FILE_BACKUP_COUNT`
- `SUBSYSTEM_LOGS_ENABLED`
- `SUBSYSTEM_LOG_DIRECTORY`

## 12. Dependencies

### 12.1 Python dependencies

Declared primarily in `pyproject.toml`, with a mostly duplicated `requirements.txt` for pip-based installs.

Core runtime libraries:
- `fastapi`
- `uvicorn[standard]`
- `asyncpg`
- `aiokafka`
- `opencv-python`
- `numpy`
- `torch`
- `torchvision`
- `ultralytics`
- `trackers`
- `supervision`
- `pymilvus`
- `tritonclient[grpc]`
- `prometheus-client`
- `psutil`
- `pydantic`
- `pydantic-settings`
- `tenacity`

Developer/test dependency currently declared:
- `pytest-asyncio`

### 12.2 Infrastructure dependencies

The supplied `docker-compose.yaml` provisions:
- etcd
- MinIO
- Milvus standalone
- Triton Inference Server
- Kafka in KRaft mode
- Kafka topic bootstrap container
- node-exporter
- postgres-exporter
- Loki
- Grafana Alloy
- Prometheus
- Grafana

Important current-state note:
- PostgreSQL itself is not defined in `docker-compose.yaml`
- the backend expects a reachable external PostgreSQL instance via `DATABASE_URL`
- `postgres-exporter` is present for metrics, but it points at an external Postgres endpoint

## 13. Deployment and execution

### 13.1 Prerequisites

You need:
- Python 3.10+
- `uv` or `pip`
- a reachable PostgreSQL database
- Docker Compose v2 for the provided shared services
- model assets expected by Triton and the tracking/ReID components
- RTSP-reachable cameras for live operation

Optional but recommended:
- `ffprobe` in `PATH` for camera validation
- PyAV (`av`) if you want the documented validator fallback when `ffprobe` is unavailable
- GPU support for Triton and heavy vision workloads

### 13.2 Boot shared infrastructure

From `backend/`:

```bash
docker compose up -d etcd minio milvus kafka kafka-init triton
```

Optional observability stack:

```bash
docker compose up -d prometheus grafana loki alloy node-exporter postgres-exporter
```

### 13.3 Prepare Python environment

Using `uv`:

```bash
uv sync
```

Or with pip:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 13.4 Create `.env`

Minimal example:

```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/rtsp_camera
CORS_ORIGINS=http://localhost:3000
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
TRITON_URL=localhost:8001
TRACKING_IDENTITY_STORE_URI=http://localhost:19530
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
```

Notes:
- the default configuration in `src/core/config.py` points `TRACKING_IDENTITY_STORE_URI` at a local file under `runtime/milvus_tracking.db`; overriding it to `localhost:19530` switches you to the external Milvus service exposed by Docker Compose
- if `ffprobe` is not in `PATH`, camera validation will attempt the PyAV fallback if `av` is installed

### 13.5 Apply database migrations manually if desired

```bash
uv run python -m src.utils.migration_runner
```

The same migrations also run automatically on startup when `RUN_MIGRATIONS_ON_STARTUP=true`.

### 13.6 Run the FastAPI control plane

From `backend/`:

```bash
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Production-style without reload:

```bash
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### 13.7 Run the OpenCV edge worker

From `backend/`:

```bash
uv run python main.py
```

The worker will:
- connect to PostgreSQL
- load active cameras
- spawn capture workers for cameras whose `status` is `active`
- refresh the camera inventory periodically

Note:
- if API and worker run on the same host with metrics enabled, give them different `METRICS_PORT` values; both runtimes default to `9109` and will otherwise compete for the same listener

### 13.8 Access points

Default endpoints from the current configuration:
- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- metrics: `http://localhost:<METRICS_PORT>/metrics` on each process that has metrics enabled
- Triton HTTP: `http://localhost:8000`
- Triton gRPC: `localhost:8001`
- Triton metrics: `http://localhost:8002/metrics`
- Kafka broker: `localhost:9092`
- Milvus gRPC/API port: `localhost:19530`
- Milvus health: `http://localhost:9091/healthz`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001`

Important port note:
- the API defaults to port `8000`
- the provided Triton container also maps HTTP to host port `8000`
- do not run both on the same host/port at the same time without changing one of the bindings

## 14. Observability

### 14.1 Metrics in code

The backend defines application metrics for:
- frames received and dropped
- frame processing latency
- queue depth
- tracking active tracks
- websocket connections and sends
- Kafka publish/consume success and failure
- dependency health
- inference ingress backpressure
- system CPU, memory, and network usage

### 14.2 Metrics collectors

- `SystemMetricsCollector` samples psutil-based host/process metrics and queue depth
- `RuntimeMetricsCollector` samples health snapshots from long-lived services such as the Kafka producer and consumer
- `HttpMetricsMiddleware` records per-route request counts and duration histograms in the API process

### 14.3 Logging

Logging is configured through `src/core/logger/logger.py` and supports:
- standard or JSON logs
- rotating file logs under `runtime/logs/`
- dedicated rotating subsystem logs under `runtime/logs/subsystems/`:
  - `streaming/`
  - `person_detection/`
  - `tracker/`
  - `body_inference/`
  - `milvus/`
  - `inference/`

### 14.4 Dashboards and monitoring assets

Additional assets live under:
- `observability/prometheus/`
- `observability/grafana/`
- `observability/loki/`
- `observability/alloy/`
- `observability/kafka_jmx/`

## 15. Maintenance notes and extension guidance

### 15.1 If you add new Kafka-backed event types

You usually need to update all of the following:
- producer code and payload schema under `src/schemas/`
- topic name in `Settings`
- `docker-compose.yaml` topic bootstrap in `kafka-init`
- `StreamEventConsumer` subscription list if the API should rebroadcast it
- frontend websocket consumers if clients need to render it

### 15.2 If you add a new pipeline stage

Most changes belong in:
- `src/opencv_pipeline/runtime.py` for stage orchestration
- a new submodule under `src/opencv_pipeline/`
- `src/opencv_pipeline/contracts.py` if the stage adds data to the shared frame/track contracts
- `OutputDispatcher` and/or metrics if the new stage emits externally visible state

### 15.3 If you add a new inference strategy

You will likely need to update:
- `InferenceWorkerConfig`
- `BatchBuilder`
- Triton model deployment/configuration
- `DecisionEngine`
- the route-level strategy values accepted by `PATCH /streams/{camera_id}/inference`

### 15.4 If you add a new persistence model

Follow the current repository pattern:
- add numbered SQL migration(s)
- add parameterized SQL under `scripts/sql/`
- add repository methods under `src/services/...`
- keep schema definitions and repositories aligned; the current `inference_events` area is an example of what happens when they drift

## 16. Known implementation realities

These are important for anyone maintaining the system:

1. The current backend is split into two Python runtimes, not one monolith process.
2. PostgreSQL is required but not containerized by the provided compose file.
3. The `stream_state` schema exists, but the currently exposed API surface is focused on camera CRUD, health, and inference toggling.
4. `camera.status` and `camera.events` are provisioned Kafka topics but are not actively used by the current Python application logic.
5. The checked-in inference-event migration does not match the active repository write shape and should be reconciled.
6. Triton and FastAPI both want host port `8000` by default, so local deployment needs explicit port planning.

## 17. Quick start checklist

1. start PostgreSQL externally and set `DATABASE_URL`
2. start Kafka, Milvus, and Triton from `docker-compose.yaml`
3. install Python dependencies
4. create `.env`
5. run migrations
6. start the FastAPI app: `uv run uvicorn src.main:app --host 0.0.0.0 --port 8000`
7. start the worker: `uv run python main.py`
8. register cameras through `POST /cameras`
9. set camera `status` to `active`
10. watch events on `WS /streams/ws/updates`

## 18. Related code-level references

Useful files for maintainers:
- `src/main.py` - API lifecycle wiring
- `main.py` - worker lifecycle wiring
- `src/core/config.py` - full configuration surface
- `src/opencv_pipeline/runtime.py` - worker orchestration
- `src/opencv_pipeline/output/publisher.py` - event emission
- `src/services/inference/manager.py` - inference lifecycle
- `src/services/inference/orchestrator.py` - Triton execution path
- `src/services/stream/kafka_event_consumer.py` - Kafka to websocket bridge
- `src/services/camera/camera_service.py` - camera business logic
- `docs/opencv_pipeline_architecture.md` - deeper stage-by-stage pipeline notes
- `docs/observability.md` - observability-specific notes
