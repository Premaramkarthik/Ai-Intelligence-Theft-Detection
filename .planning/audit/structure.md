# Repository Structural Map

**Generated:** 2026-03-14
**Repository:** `pipeline_opencv` (branch: `v3`)
**Purpose:** Real-time AI-powered shoplifting detection and surveillance pipeline.

---

## Table of Contents

1. [Repository Overview](#repository-overview)
2. [Top-Level Layout](#top-level-layout)
3. [Backend — Shared Package](#backend--shared-package)
4. [Backend — Inference Service](#backend--inference-service)
5. [Backend — MediaBridge Service](#backend--mediabridge-service)
6. [Backend — Signaling Service](#backend--signaling-service)
7. [Backend — Alerting Service](#backend--alerting-service)
8. [Backend — Persistence Service](#backend--persistence-service)
9. [Backend — Tests](#backend--tests)
10. [Backend — Infrastructure](#backend--infrastructure)
11. [Frontend — App Pages](#frontend--app-pages)
12. [Frontend — Components](#frontend--components)
13. [Frontend — Hooks](#frontend--hooks)
14. [Frontend — Stores](#frontend--stores)
15. [Frontend — Lib Utilities](#frontend--lib-utilities)
16. [Data Flow & Message Contracts](#data-flow--message-contracts)
17. [Redis Key Space](#redis-key-space)
18. [Prometheus Metrics Ports](#prometheus-metrics-ports)
19. [Environment Variables](#environment-variables)

---

## Repository Overview

This is a production-grade, microservices real-time video inference pipeline. Five independent Python backend services communicate exclusively via **Redis** (pub/sub, streams, and key-value), sharing zero direct inter-service calls. A Next.js 16 frontend communicates with the **Signaling** service over REST and WebSocket.

**Domain:** Retail loss-prevention via shoplifting detection.

**Core pipeline stages (D1–D5):**
- **D1 (MediaBridge):** Camera ingestion → shared-memory ring buffer + Redis frame pointer
- **D2 (Inference / ObjectDetector):** YOLO person+item detection and ByteTrack tracking
- **D3 (Inference / ItemInteraction):** Hand-proximity state machine trigger
- **D4 (Inference / BehaviorClassifier):** CNN+Transformer temporal classification
- **D5 (Alerting):** Telegram dispatch + MQTT publish; Persistence DB write

---

## Top-Level Layout

```
pipeline_opencv/
├── backend/                    # All Python microservices
│   ├── docker-compose.yml      # Full stack orchestration
│   ├── docker/                 # Per-service Dockerfiles + mosquitto.conf
│   ├── pyproject.toml          # Project metadata, deps, tool config (uv/ruff/mypy/pytest)
│   ├── requirements.txt        # Flat pip requirements (mirrors pyproject.toml deps)
│   ├── uv.lock                 # Locked dependency manifest (uv)
│   ├── .env                    # Local environment variables (gitignored secrets)
│   ├── .python-version         # Python version pin
│   ├── .pre-commit-config.yaml # pre-commit hooks
│   ├── .pylintrc               # Pylint config
│   ├── models/                 # Binary model files (not in git content)
│   │   ├── yolo/yolo26n.engine         # TensorRT engine (person+item detector)
│   │   ├── yolo/yolo26n.onnx           # ONNX source
│   │   ├── shoplifting/cnn_transformer.engine  # TensorRT engine (behavior classifier)
│   │   ├── shoplifting/cnn_transformer.onnx    # ONNX source (NCHW layout)
│   │   ├── shoplifting/cnn_transformer_ncdhw.onnx  # ONNX source (NCDHW layout)
│   │   └── ...
│   ├── services/               # Five microservices
│   │   ├── inference/
│   │   ├── mediabridge/
│   │   ├── signaling/
│   │   ├── alerting/
│   │   └── persistence/
│   ├── shared/                 # Cross-service shared library
│   │   ├── core/               # Settings, ConfigManager
│   │   ├── db/                 # asyncpg pool
│   │   ├── logging/            # JSON + Redis log handler
│   │   ├── shm/                # Shared memory ring buffer
│   │   └── types/              # Pydantic event schemas + dataclass models
│   ├── scripts/
│   │   ├── schema.sql          # PostgreSQL DDL (detection_events, partitioned)
│   │   ├── run_local.sh / .cmd # Local dev launcher scripts
│   │   └── cleanup.sh / .cmd   # Kill stale processes
│   ├── tests/                  # Pytest unit + integration tests
│   └── docs/                   # Architecture and service documentation
│
├── frontend/                   # Next.js 16 / React 19 dashboard
│   ├── package.json            # Node deps (Next, React, Zustand, TanStack Query, Tailwind)
│   ├── next.config.ts          # Minimal Next.js config
│   ├── tsconfig.json           # TypeScript strict config, @/* alias
│   ├── eslint.config.mjs       # ESLint config
│   ├── postcss.config.mjs      # PostCSS / Tailwind v4
│   ├── .env                    # Frontend env vars (NEXT_PUBLIC_API_BASE_URL)
│   └── src/
│       ├── app/                # Next.js App Router pages
│       ├── components/         # React components
│       ├── hooks/              # Custom React hooks
│       ├── stores/             # Zustand global state
│       └── lib/                # Utility functions
│
├── logs/                       # Runtime log files (one per service, .out/.err)
├── start.cmd                   # Windows launcher: starts backend stack + Next.js frontend
├── stop.cmd                    # Windows stop script
├── start.sh                    # (implied) Linux launcher
└── .gitignore
```

---

## Backend — Shared Package

**Root:** `backend/shared/`

All five services import from this package. It is the single source of truth for configuration, data contracts, and cross-cutting concerns.

---

### `backend/shared/core/settings.py`

**Purpose:** Central Pydantic `BaseSettings` singleton. All configuration is read from environment variables (or `.env` file) through this class.

**Key class:** `Settings(BaseSettings)`

| Field | Default | Description |
|---|---|---|
| `redis_url` (property) | computed | Builds URL from host/port/password or uses `REDIS_URL` env |
| `db_url` (property) | computed | PostgreSQL DSN |
| `shm_slots_per_cam` | 32 | Ring buffer slots per camera |
| `frame_width` / `frame_height` | 1280 / 720 | Canonical frame resolution |
| `frame_queue_maxlen` | 256 | Max Redis `frames` list length before backpressure drop |
| `detector_engine_path` | `models/yolo/yolo26n.engine` | TensorRT detector |
| `classifier_engine_path` | `models/shoplifting/cnn_transformer.engine` | TensorRT classifier |
| `temporal_window` | 16 | Number of frames in behavior classification clip |
| `default_confidence_threshold` | 0.7 | Detection confidence filter |
| `hand_dist_px` | 80 | Pixel distance threshold for interaction trigger |
| `interaction_frames` | 5 | Consecutive frames before interaction fires |
| `alert_confidence_threshold` | 0.8 | Minimum confidence to dispatch Telegram alert |
| `camera_stream_fps` | 15 | WebSocket camera stream target FPS |
| `config_poll_interval_s` | 5 | How often inference re-reads camera config from Redis |

**Exported:** `get_settings() -> Settings` (LRU-cached singleton)

**Dependencies:** `pydantic-settings`, `os`, `urllib.parse`

---

### `backend/shared/core/config.py`

**Purpose:** `ConfigManager` — polls Redis `config:<camera_id>` hashes periodically and makes camera-specific configuration available to inference workers.

**Key classes:**
- `CameraConfig` (dataclass): per-camera inference parameters (roi, confidence_threshold, iou_threshold, hand_dist_px, min_displacement_px, interaction_frames, enabled)
- `ConfigManager`: async Redis poller with `start()`, `stop()`, `poll_loop()`, `get(camera_id)`, `set(camera_id, cfg)` methods

**Dependencies:** `redis.asyncio`, `shared.core.settings`, `shared.logging.logger`

---

### `backend/shared/shm/ring_buffer.py`

**Purpose:** Zero-copy shared-memory ring buffer for frame transport between **MediaBridge** (writer process) and **Inference** (reader process). Uses Python's `multiprocessing.shared_memory`.

**Key classes:**
- `RingBufferWriter`: allocates three SHM blocks per camera (`cam_{id}_ring` for frame data, `cam_{id}_idx` for atomic write index, `cam_{id}_gen` for generation counters). `write(frame) -> (slot_id, generation)`.
- `RingBufferReader`: attaches to existing SHM blocks. `read(slot_id, expected_generation) -> np.ndarray` — returns a copy with stale-frame protection.
- `ReaderCache`: class-level dict cache for `RingBufferReader` instances with 3-retry attach logic.

**SHM naming convention:** `cam_{camera_id}_ring`, `cam_{camera_id}_idx`, `cam_{camera_id}_gen`

**Dependencies:** `multiprocessing.shared_memory`, `numpy`, `ctypes`

---

### `backend/shared/types/events.py`

**Purpose:** Pydantic v2 message schema definitions. These are the **wire contracts** between services over Redis pub/sub and Redis Streams.

**Key models:**

| Model | Used by | Description |
|---|---|---|
| `FrameTelemetryMessage` | Inference → Signaling | Per-frame detection results, published to `telemetry:{camera_id}` |
| `IncidentEvent` | Inference → Alerting/Persistence | Full incident record, pushed to `stream:incidents` |
| `CameraStreamMessage` | Signaling → Frontend WS | Base64 JPEG + detections for `/ws/camera/{id}` |
| `DetectionPayload` | Embedded | Single bounding box (bbox, label, confidence, track_id) |
| `IncidentPayload` | Embedded | Incident summary (label, confidence, severity) |
| `FrameReference` | Embedded | SHM pointer (camera_id, slot_id, generation) |
| `HistoryEvent` | Signaling → Frontend REST | Flattened DB row for `/api/events` response |
| `MessageType` (StrEnum) | All | `telemetry.frame`, `incident.event`, `camera.stream`, `system.status` |
| `Severity` (StrEnum) | All | `info`, `low`, `medium`, `high`, `critical` |

`SCHEMA_VERSION = 1` — integer embedded in all messages.

**Dependencies:** `pydantic`, `datetime`, `uuid`

---

### `backend/shared/types/models.py`

**Purpose:** Low-level dataclass types used within service boundaries (not sent over wire directly).

**Key types:**

| Type | Description |
|---|---|
| `BBox` | Pixel-coordinate bounding box with `.iou()`, `.center`, `.area` |
| `Detection` | Single-frame object detection result (BBox, confidence, class_id, class_name, mask, keypoints) |
| `TrackedPerson` | ByteTrack-assigned person with track_id and optional segmentation mask |
| `FramePointer` | Lightweight Redis payload: camera_id + slot_id + generation + t_capture + trace_id. Has `.to_bytes()` / `.from_bytes()` (JSON-encoded) |
| `InteractionState` (Enum) | IDLE / WATCHING / TRIGGERED |
| `TrackState` | Per-track state for interaction state machine |
| `DetectionEvent` | Simple dataclass for persistence queue (not currently used in main path) |

---

### `backend/shared/logging/logger.py`

**Purpose:** Structured JSON logging with dual output: stdout and Redis pub/sub channel `logs`.

**Key exports:**
- `get_logger(name, level) -> logging.Logger` — idempotent, attaches `_JsonFormatter` and optionally `RedisLogHandler`
- `root` — module-level root pipeline logger

**`RedisLogHandler`:** Publishes each log record to Redis channel `"logs"` using a synchronous `redis` client. Enabled when `ENABLE_REDIS_LOGS=true` (default).

**Dependencies:** `redis` (sync), `shared.core.settings`

---

### `backend/shared/db/session.py`

**Purpose:** asyncpg connection pool manager. Used by **Signaling** (read-only queries) and **Persistence** (writes).

**Key class:** `DatabaseSession`
- `connect()`: creates pool (min 2, max `postgres_pool_size`)
- `disconnect()`: closes pool
- `get_pool() -> asyncpg.Pool`
- `initialize_db(schema_path)`: reads and executes `scripts/schema.sql` at startup

Note: `backend/services/persistence/db/session.py` is an **identical copy** of this file (duplication concern).

**Dependencies:** `asyncpg`, `shared.core.settings`, `shared.logging.logger`

---

## Backend — Inference Service

**Root:** `backend/services/inference/`
**Entry point:** `python -m services.inference.main`
**Prometheus metrics port:** `9101`
**Docker image:** `Dockerfile.inference` (requires CUDA/NVIDIA GPU at runtime)

---

### `backend/services/inference/main.py`

**Purpose:** Service entry point. Connects to Redis, starts Prometheus HTTP server, spawns one or more GPU inference workers.

**Key logic:**
- Reads `INFERENCE_GPU_WORKERS` env var (default: 1) to scale workers.
- Single worker path: simple `blpop` loop on Redis list `"frames"`.
- Multi-worker path: `asyncio.gather` over N `_inference_worker` coroutines, each independently `blpop`-ing from the same list (Redis list semantics ensure no duplicate consumption).
- On shutdown: clears `ReaderCache` to release SHM handles.

**Dependencies:** `redis.asyncio`, `prometheus_client`, `shared.logging.logger`, `services.inference.ml.pipeline`, `services.inference.utils.metrics`, `shared.core.settings`

---

### `backend/services/inference/ml/pipeline.py`

**Purpose:** `InferencePipeline` — the core orchestrator. Processes one frame pointer per call. Maintains per-camera `CameraRuntimeState` instances for isolation.

**Key classes:**
- `CameraConfig` (dataclass): live config (enabled, confidence_threshold, hand_dist_px, interaction_frames, loaded_at). Refreshed from Redis every `config_poll_interval_s`.
- `CameraRuntimeState` (dataclass): per-camera state including `ItemInteractionDetector`, `TemporalBuffer`, frame counters, adaptive skip_n, current incident, last detection caches.
- `InferencePipeline`:
  - `load_models()`: calls `ModelManager.preload_all()`, initializes `ReIDService`
  - `process(payload, redis)`: full per-frame pipeline
  - `_load_camera_config()`: reads `config:{camera_id}` hash from Redis
  - `_apply_reid()`: optional cross-camera person re-identification
  - `_run_classification()`: async task for temporal behavior classification
  - `_publish_telemetry()`: publishes `FrameTelemetryMessage` to `telemetry:{camera_id}` channel and caches in `telemetry:latest:{camera_id}`

**Adaptive frame skipping:** `skip_n` adjusts between 1–10 based on whether frame processing time exceeds 50ms (slow) or is under 20ms (fast).

**Redis channels written:**
- `telemetry:{camera_id}` (pub/sub) — per-frame telemetry
- `telemetry:latest:{camera_id}` (key) — latest telemetry snapshot for snapshot endpoint
- `stream:incidents` (Redis Stream) — confirmed incidents
- `incidents:{camera_id}` (pub/sub) — per-camera incident events

**Dependencies:** `redis.asyncio`, `numpy`, `services.inference.ml.engines.*`, `services.inference.ml.model_manager`, `services.inference.services.*`, `services.inference.utils.metrics`, `shared.core.settings`, `shared.logging.logger`, `shared.types.events`, `shared.types.models`

---

### `backend/services/inference/ml/model_manager.py`

**Purpose:** Singleton `ModelManager` that owns lazy-loaded GPU model instances.

**Key class:** `ModelManager` (singleton via `__new__`)
- `preload_all()`: concurrently loads detector and classifier, then warms up detector
- `get_detector(device) -> ObjectDetector`: lazy-load with async lock
- `get_behavior_classifier(device) -> BehaviorClassifier`: lazy-load with async lock
- `redis` (property): shared async Redis client
- `_detect_device()`: asserts CUDA is available; raises if not

**Dependencies:** `asyncio`, `torch`, `redis.asyncio`, `shared.core.settings`, `services.inference.ml.engines.*`

---

### `backend/services/inference/ml/engines/object_detector.py`

**Purpose:** Wrapper for the `yolo26n.engine` TensorRT YOLO model. Performs person detection + ByteTrack tracking + non-person item detection in a single call.

**Key class:** `ObjectDetector`
- `__init__(model_path, device)`: loads via `ultralytics.YOLO`. Requires `.engine` extension.
- `warmup(imgsz)`: runs 3 dummy predictions
- `detect_and_track(frame, tracker_id) -> DetectionResult`

**`DetectionResult`** (dataclass): `person_boxes: list`, `person_masks: list`, `track_ids: list`, `items: list[dict]`

Persons (class 0) and all other classes are separated. Non-person items include bbox, cls int, label string, conf float.

**Dependencies:** `ultralytics.YOLO`, `numpy`, `shared.logging.logger`

---

### `backend/services/inference/ml/engines/behavior_classifier.py`

**Purpose:** Wrapper for the `cnn_transformer.engine` TensorRT model. Runs temporal video clip classification (shoplifting vs. normal).

**Key class:** `BehaviorClassifier`
- `__init__(model_path, device, clip_frames)`: loads TensorRT engine and creates CUDA context and stream. Requires `tensorrt` and `cuda` Python bindings.
- `_preprocess(clip) -> np.ndarray`: resizes to 224×224, ImageNet normalize, stacks to `(1, T, C, H, W)` float32
- `_infer(input_tensor) -> np.ndarray`: runs TRT execute_async_v3 with explicit tensor addressing
- `classify(clip) -> (label, confidence)`: async wrapper. Returns `("shoplifting", score)` if score > 0.5, else `("normal", 1-score)`.

**`TensorBinding`** (dataclass): name, dtype, is_input, shape, ptr (CUDA device pointer), nbytes

**Hard requirements:** CUDA device, TensorRT Python bindings, cuda-python package.

**Dependencies:** `tensorrt`, `cuda.cudart`, `cv2`, `numpy`, `shared.logging.logger`

---

### `backend/services/inference/ml/engines/background_blur.py`

**Purpose:** `BackgroundBlur` — Gaussian blur applied to non-person pixels using segmentation masks from YOLO. Person regions remain sharp.

**Key class:** `BackgroundBlur`
- `apply(frame, masks) -> np.ndarray`: handles both list-of-masks and ndarray masks, broadcasts to 3D for numpy.where

**Dependencies:** `cv2`, `numpy`

---

### `backend/services/inference/ml/engines/__init__.py`

Re-exports `ObjectDetector`, `BackgroundBlur`, `BehaviorClassifier` from this package.

---

### `backend/services/inference/services/interaction.py`

**Purpose:** `ItemInteractionDetector` — proximity-based temporal gate state machine. Counts consecutive frames where a tracked person is near a detected item. Fires `should_classify()` when threshold is reached.

**Key class:** `ItemInteractionDetector`
- State: `_states: dict[track_id, frame_count]`, `_tracks: dict[track_id, last_seen]`
- `update(tracks, detections)`: increments counters and sets `_should_classify = True` when `frame_count >= interaction_frames`
- `delete_stale_tracks()`: removes tracks inactive for `TRACK_TIMEOUT_S = 30.0` seconds
- `configure(hand_dist_px, interaction_frames)`: hot-reconfigures without resetting state
- `should_classify() -> bool`: read by pipeline to trigger classifier

**Note:** Current proximity logic is a simplified counter (each frame with any detection increments). The actual hand-distance spatial check is marked as mock.

**Dependencies:** `time`, `shared.logging.logger`

---

### `backend/services/inference/services/reid_service.py`

**Purpose:** `ReIDService` — cross-camera person re-identification using appearance embeddings stored in Redis.

**Key class:** `ReIDService`
- Feature extractor: MobileNetV3-Small with classifier head removed (576-dim L2-normalized embeddings)
- `extract_features(person_crop) -> np.ndarray`: BGR crop → PIL → torchvision transforms → MobileNet → L2-norm
- `get_global_id(embedding) -> str | None`: cosine similarity scan of all `reid:embeddings:*` keys in Redis. Returns best match ID if similarity > threshold (0.7). **MVP: linear scan of all keys (production should use RediSearch HNSW).**
- `register_track(global_id, embedding)`: stores bytes in Redis with 3600s TTL

**Dependencies:** `torch`, `torchvision.models`, `cv2`, `PIL`, `numpy`, `redis.asyncio`, `shared.logging.logger`

---

### `backend/services/inference/services/temporal_buffer.py`

**Purpose:** `TemporalBuffer` — circular deque of frame copies for behavior classification.

**Key class:** `TemporalBuffer`
- `push(frame)`: appends a copy (not a view)
- `get_clip() -> list[np.ndarray]`: returns current frames as a list
- `__len__`: current buffer size

**Dependencies:** `collections.deque`, `numpy`

---

### `backend/services/inference/utils/metrics.py`

**Purpose:** Prometheus metric definitions for the Inference service.

| Metric | Type | Description |
|---|---|---|
| `inference_latency_seconds` | Histogram | End-to-end per-frame D1→D5 latency |
| `inference_frames_processed_total` | Counter | Successfully processed frames |
| `inference_frames_dropped_total` | Counter | Stale/unreadable frames skipped |
| `inference_gpu_memory_bytes` | Gauge | Current GPU memory usage |
| `METRICS_PORT = 9101` | constant | Prometheus scrape port |

---

### `backend/services/inference/utils/shm_reader.py`

**Purpose:** Thin `SHMReader` wrapper around `RingBufferReader`. Used in tests / utility contexts.

**Dependencies:** `shared.shm.ring_buffer.RingBufferReader`, `numpy`

---

## Backend — MediaBridge Service

**Root:** `backend/services/mediabridge/`
**Entry point:** `python -m services.mediabridge.main`
**Prometheus metrics port:** `9102`
**Docker:** `Dockerfile.mediabridge`, `ipc: host` (shares `/dev/shm` with inference)

---

### `backend/services/mediabridge/main.py`

**Purpose:** Camera supervisor. Polls Redis hash `camera_sources` every 5 seconds and starts/stops `CameraWorker` instances accordingly. Handles worker crashes with automatic restart. Clears stale `frame_ptr:*` keys from prior runs on startup.

**Key logic:**
- `active_workers: dict[camera_id, (CameraWorker, asyncio.Task)]`
- Adds workers for new camera IDs, cancels workers for removed IDs
- On worker crash: logs error, starts fresh `CameraWorker` instance

**Dependencies:** `redis.asyncio`, `prometheus_client`, `services.mediabridge.services.camera_worker`, `shared.core.settings`, `shared.logging.logger`

---

### `backend/services/mediabridge/services/camera_worker.py`

**Purpose:** `CameraWorker` — per-camera capture loop. Reads frames from a video source, resizes to canonical resolution, writes to SHM ring buffer, pushes `FramePointer` JSON to Redis list `"frames"` and updates `frame_ptr:{camera_id}` key.

**Key behavior:**
- Reconnects with exponential backoff (cap: 30s) after `MAX_CONSECUTIVE_FAILURES = 10` consecutive read failures
- Backpressure: if `llen("frames") >= frame_queue_maxlen`, pops oldest frame before pushing new one
- Sets `camera_status:{camera_id}` Redis key to `"online"`, `"reconnecting"`, or `"offline"`
- Frame rate limiting: sleeps `frame_interval_s = 1 / camera_stream_fps`
- Color normalization: converts grayscale and BGRA frames to BGR

**Dependencies:** `cv2`, `uuid`, `redis.asyncio`, `shared.types.models.FramePointer`, `shared.core.settings`, `services.mediabridge.services.shm_writer`, `services.mediabridge.sources.sources`, `services.mediabridge.utils.metrics`

---

### `backend/services/mediabridge/services/shm_writer.py`

**Purpose:** `SHMWriter` — thin wrapper around `RingBufferWriter`. `write(frame) -> (slot_id, generation)`. `close()` unlinks SHM blocks.

**Dependencies:** `shared.shm.ring_buffer.RingBufferWriter`, `numpy`

---

### `backend/services/mediabridge/sources/sources.py`

**Purpose:** Video source abstraction layer. Provides `BaseSource` interface and concrete implementations. `get_source(src)` factory dispatches by type.

**Key classes:**

| Class | Trigger | Description |
|---|---|---|
| `OpenCVSource` | file paths, generic URLs | `cv2.VideoCapture` wrapper |
| `FFmpegSource` | `rtsp://` or `http` URLs | Pipes raw BGR24 frames from an FFmpeg subprocess. Uses NVDEC hardware decode if `nvidia-smi` is present. Drains stderr in a background thread to prevent pipe deadlock. |
| `WebcamSource(OpenCVSource)` | integer device index (or numeric string) | V4L2 backend on Linux |
| `RTSPSource(FFmpegSource)` | explicit RTSP URL | Same as FFmpegSource with logging |

**`validate_source(src, timeout_s=3.0) -> bool`:** Quick OpenCV-based readability check used by Signaling before registering a camera.

**`get_source(src) -> BaseSource`:** Factory. Numeric string → WebcamSource. Integer → WebcamSource. `rtsp://` or `http` → FFmpegSource. Otherwise → OpenCVSource.

**Dependencies:** `cv2`, `subprocess`, `threading`, `numpy`, `shutil`, `shared.logging.logger`

---

### `backend/services/mediabridge/utils/metrics.py`

**Purpose:** Prometheus metrics for MediaBridge.

| Metric | Type | Labels |
|---|---|---|
| `mediabridge_frames_captured_total` | Counter | `camera_id` |
| `mediabridge_frames_dropped_total` | Counter | `camera_id` |
| `mediabridge_cameras_active` | Gauge | — |
| `mediabridge_capture_latency_ms` | Gauge | `camera_id` |

---

## Backend — Signaling Service

**Root:** `backend/services/signaling/`
**Entry point:** `uvicorn services.signaling.main:app --port 9000` (Docker) / `--port 9001` (local dev)
**Prometheus metrics port:** `9100` (via `/metrics` ASGI mount)
**Docker:** `Dockerfile.signaling` (runs as non-root `appuser`)

The only public-facing HTTP/WebSocket service. Aggregates all frontend-facing APIs.

---

### `backend/services/signaling/main.py`

**Purpose:** FastAPI application factory (`create_app()`). Configures CORS, rate limiting (slowapi), Prometheus metrics ASGI mount, and lifespan startup/shutdown.

**`lifespan`:** connects Redis and PostgreSQL pool; on shutdown clears `ReaderCache` and closes connections.

**Security check:** In non-development environments, rejects wildcard CORS and requires JWT/admin credentials configured.

**`app = create_app()`** is the module-level ASGI app.

**Dependencies:** `fastapi`, `redis.asyncio`, `prometheus_client`, `slowapi`, `shared.core.settings`, `shared.db.session`, `services.signaling.api.router`

---

### `backend/services/signaling/api/router.py`

**Purpose:** Central `api_router` aggregating all route modules.

**Route table:**

| Router | Prefix | Tags |
|---|---|---|
| `health` | (root) | health |
| `status` | `/api` | status |
| `auth` | `/auth` | auth |
| `config` | `/api` | config |
| `system_status` (WS) | (root) | ws |
| `camera` | `/api` | camera |
| `cameras` | `/api/cameras` | cameras |
| `events` | `/api` | events |
| `alerts` | `/api/alerts` | alerts |
| `predictions` (WS) | (root) | ws |
| `camera_stream` (WS) | (root) | ws |
| `logs` (WS) | (root) | ws |

---

### `backend/services/signaling/api/routes/auth.py`

**Endpoint:** `POST /auth/token`

Validates username/password against `ADMIN_USERNAME` / `ADMIN_PASSWORD` settings. Returns `TokenResponse(access_token, token_type="bearer")`.

**Dependencies:** `fastapi.security.OAuth2PasswordRequestForm`, `services.signaling.core.security`, `shared.core.settings`

---

### `backend/services/signaling/api/routes/camera.py`

**Endpoints:**
- `GET /api/camera/{camera_id}/snapshot` — returns latest JPEG frame from SHM (authenticated)
- `POST /api/camera/connect` — registers a new camera source (webcam or RTSP). Validates source readability via `validate_source()`. Writes to `camera_sources` Redis hash and seeds default `config:{cam_id}` if not present.

**Dependencies:** `services.signaling.services.camera_service.grab_jpeg`, `services.mediabridge.sources.sources.validate_source`, `services.signaling.schemas.camera`

---

### `backend/services/signaling/api/routes/cameras.py`

**Endpoints:**
- `GET /api/cameras/` — returns `camera_sources` Redis hash (all camera IDs and their source URLs)
- `DELETE /api/cameras/{camera_id}` — removes camera from `camera_sources`, deletes `config:` and `frame_ptr:` keys

---

### `backend/services/signaling/api/routes/config.py`

**Endpoints:**
- `PUT /api/config/{camera_id}` — writes ROI config to `config:{camera_id}` Redis hash
- `GET /api/config/{camera_id}` — reads and returns `ROIConfigResponse`

**Schema:** `ROIConfigRequest` (roi dict, confidence_threshold, iou_threshold, hand_dist_px, enabled)

---

### `backend/services/signaling/api/routes/events.py`

**Endpoint:** `GET /api/events?limit=50`

Queries `detection_events` PostgreSQL table ordered by `created_at DESC`. Returns list of `HistoryEvent` Pydantic models serialized to JSON.

**Dependencies:** `shared.types.events.HistoryEvent`, asyncpg pool via `request.app.state.db`

---

### `backend/services/signaling/api/routes/alerts.py`

**Endpoint:** `POST /api/alerts/trigger`

Manual alert injection. Creates `IncidentEvent` and pushes to Redis Stream `stream:incidents` and pub/sub `incidents:{camera_id}`.

---

### `backend/services/signaling/api/routes/status.py`

**Endpoint:** `GET /api/status`

Returns aggregated system health: Redis ping, camera source counts vs. active frame pointers, NVIDIA GPU stats (via pynvml if available), CPU/RAM via psutil.

---

### `backend/services/signaling/api/routes/health.py`

**Endpoints:**
- `GET /health/live` — liveness: returns `{"status": "ok"}`
- `GET /health/ready` — readiness: pings Redis and PostgreSQL, checks JWT/model config
- `GET /health` — simple health check

**Note:** `/health/ready` references `settings.model_engine_path` which does not exist in `Settings`. This will raise `AttributeError` at runtime (bug).

---

### `backend/services/signaling/api/deps.py`

**Purpose:** FastAPI dependency functions.

- `get_redis(request) -> aioredis.Redis`: returns `request.app.state.redis`
- `verify_jwt(token) -> str`: decodes Bearer token, raises HTTP 401 on failure
- `verify_ws_token(websocket) -> str`: extracts token from query param `?token=` or `Authorization` header

**Dependencies:** `jose.JWTError`, `fastapi.security.OAuth2PasswordBearer`, `services.signaling.core.security`

---

### `backend/services/signaling/core/security.py`

**Purpose:** JWT creation and decoding using `python-jose`.

- `create_access_token(username) -> str`: encodes `{"sub": username, "exp": now + jwt_expire_minutes}`
- `decode_token(token) -> str`: validates and returns `sub` claim

**Dependencies:** `jose.jwt`, `shared.core.settings`

---

### `backend/services/signaling/schemas/camera.py`

**Purpose:** Pydantic schemas for camera API.

| Schema | Fields |
|---|---|
| `ROIConfigRequest` | roi (dict), confidence_threshold (0.45), iou_threshold (0.15), hand_dist_px (80), enabled (True) |
| `ROIConfigResponse` | extends ROIConfigRequest + camera_id |
| `RTSPConfig` | rtsp_url (str) |
| `CameraConnectRequest` | source_type ("rtsp"\|"webcam"), rtsp_config (optional RTSPConfig) |
| `ConnectResponse` | status, message, stream_ids (list[str]) |

---

### `backend/services/signaling/schemas/auth.py`

`TokenResponse`: access_token (str), token_type ("bearer")

---

### `backend/services/signaling/services/camera_service.py`

**Purpose:** Core helper functions for camera snapshot and stream message construction.

- `grab_jpeg(redis, camera_id) -> bytes | None`: reads `frame_ptr:{camera_id}`, deserializes `FramePointer`, attaches to SHM via `ReaderCache`, JPEG-encodes (quality 80) with `cv2.imencode`
- `grab_metadata(camera_id, redis) -> dict`: reads `telemetry:latest:{camera_id}` JSON
- `build_stream_message(camera_id, jpeg, metadata) -> dict`: constructs `CameraStreamMessage` with base64-encoded JPEG

**Dependencies:** `cv2`, `base64`, `shared.shm.ring_buffer.ReaderCache`, `shared.types.events.CameraStreamMessage`, `shared.types.models.FramePointer`

---

### `backend/services/signaling/ws/camera_stream.py`

**Endpoint:** `WebSocket /ws/camera/{camera_id}`

Authenticated. Streams camera frames at `camera_stream_fps` by calling `grab_jpeg` + `grab_metadata` concurrently every interval, builds `CameraStreamMessage`, sends as JSON text.

---

### `backend/services/signaling/ws/predictions.py`

**Endpoint:** `WebSocket /ws/predictions`

Authenticated. Subscribes to Redis pub/sub patterns `telemetry:*` and `incidents:*` via `psubscribe`. Forwards every `pmessage` directly to the WebSocket client as text. This is the frontend's real-time inference stream.

---

### `backend/services/signaling/ws/system_status.py`

**Endpoint:** `WebSocket /ws/status`

Authenticated. Sends a JSON payload every 1 second containing:
- `ts`: Unix timestamp
- `system`: cpu_usage, ram_usage (via psutil)
- `gpu`: NVML stats (total/used/free MB, utilization %) — cached for 5s to avoid polling overhead

---

### `backend/services/signaling/ws/logs.py`

**Endpoint:** `WebSocket /ws/logs`

**No authentication required** (potential concern). Subscribes to Redis pub/sub channel `"logs"` and forwards log records as text. This is how structured JSON logs from all services stream to the frontend.

---

## Backend — Alerting Service

**Root:** `backend/services/alerting/`
**Entry point:** `python -m services.alerting.main`
**Prometheus metrics port:** `9103`

---

### `backend/services/alerting/main.py`

**Purpose:** Consumes `stream:incidents` Redis Stream via consumer group `alerting_group` / consumer `alerting_worker_0`. For each incident with `confidence >= alert_confidence_threshold`: dispatches Telegram alert and MQTT publish, then `xack`s the message.

**Consumer group:** Created at startup via `xgroup_create` with `mkstream=True` (idempotent via BUSYGROUP guard).

**Read pattern:** `xreadgroup` with `count=10, block=1000ms`

**Dependencies:** `redis.asyncio`, `prometheus_client`, `services.alerting.services.telegram`, `services.alerting.services.mqtt`, `shared.types.events.IncidentEvent`, `shared.core.settings`

---

### `backend/services/alerting/services/telegram.py`

**Purpose:** `TelegramService` — sends formatted shoplifting alerts to Telegram using `python-telegram-bot` (v20+).

**Key class:** `TelegramService`
- Circuit breaker: CLOSED → OPEN after 5 consecutive failures, recovers to HALF_OPEN after 30s
- Retry: up to 3 attempts with delays [1, 2, 4]s; handles `RetryAfter` (flood control), `TimedOut`, `NetworkError`
- `send_shoplifting_alert(camera_id, confidence, timestamp)`: formats Markdown message and calls `send_alert`
- `initialize()`: auto-discovers chat IDs from `bot.get_updates()` if `TELEGRAM_ADMIN_CHAT_IDS` not set
- Chat IDs are comma-separated from `TELEGRAM_ADMIN_CHAT_IDS` env var

**Dependencies:** `telegram.Bot`, `telegram.error.*`, `shared.core.settings`, `shared.logging.logger`

---

### `backend/services/alerting/services/mqtt.py`

**Purpose:** `MQTTService` — currently a **stub/mock** implementation. `publish(topic, payload)` only logs; no actual MQTT connection. Real implementation would use `gmqtt` or `paho`.

**Dependencies:** `shared.logging.logger`, `shared.core.settings`

---

### `backend/services/alerting/utils/metrics.py`

`alerts_sent` Counter — total alerts dispatched. `METRICS_PORT = 9103`.

---

## Backend — Persistence Service

**Root:** `backend/services/persistence/`
**Entry point:** `python -m services.persistence.main`
**Prometheus metrics port:** `9104`
**Docker:** `Dockerfile.persistence` (copies `scripts/` for schema.sql)

---

### `backend/services/persistence/main.py`

**Purpose:** Consumes `stream:incidents` Redis Stream via consumer group `persistence_group` / consumer `persistence_worker_0`. For each message: deserializes `IncidentEvent`, calls `DBWriter.save_event()`, then `xack`s. On graceful shutdown: drains pending (unacked) messages before exit.

**Batch size:** `count=20, block=1000ms`

**Dependencies:** `redis.asyncio`, `prometheus_client`, `services.persistence.services.writer`, `shared.core.settings`

---

### `backend/services/persistence/services/writer.py`

**Purpose:** `DBWriter` — wraps `DatabaseSession`, validates incoming dicts as `IncidentEvent`, executes `INSERT_QUERY`, measures latency via Prometheus histogram.

**`save_event(data: dict)`:** Calls `IncidentEvent.model_validate(data)` then `pool.execute(INSERT_QUERY, ...)` with 13 positional parameters.

**Dependencies:** `asyncpg`, `services.persistence.models.events.INSERT_QUERY`, `shared.db.session.DatabaseSession`, `shared.types.events.IncidentEvent`

---

### `backend/services/persistence/models/events.py`

**Purpose:** SQL constants for the persistence layer.

`TABLE_NAME = "detection_events"`

`INSERT_QUERY`: parameterized `INSERT INTO detection_events (event_id, camera_id, trace_id, event_type, class_name, confidence, severity, created_at, frame_ref, detections, metadata, schema_version, payload) VALUES ($1...$13)` with JSONB casts.

---

### `backend/services/persistence/db/session.py`

**Note:** Duplicate of `backend/shared/db/session.py`. Identical `DatabaseSession` class.

---

### `backend/services/persistence/utils/metrics.py`

`db_write_latency` Histogram — DB insert latency. `METRICS_PORT = 9104`.

---

## Backend — Tests

**Root:** `backend/tests/`
**Framework:** pytest + pytest-asyncio (`asyncio_mode = "auto"`)
**Config:** `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, `log_cli = true`, `log_level = "DEBUG"`

---

### `backend/tests/test_contracts.py`

**Purpose:** Unit tests verifying Pydantic schema round-trips for the three core message types.

**Tests:**
- `test_canonical_telemetry_schema_round_trip`: builds `FrameTelemetryMessage`, dumps to JSON, asserts field values
- `test_incident_event_contract_contains_history_fields`: builds `IncidentEvent`, asserts `event_id`, `event_type`, `severity`
- `test_camera_stream_contract_uses_single_json_message`: builds `CameraStreamMessage`, asserts `message_type`

**Dependencies:** `shared.types.events.*`

---

### `backend/tests/test_signaling_contracts.py`

**Purpose:** Unit tests for Signaling service behaviors without a running server.

**Tests:**
- `test_history_route_returns_canonical_fields`: uses fake request/DB objects to call `get_recent_events()` directly
- `test_stream_message_builder_matches_frontend_protocol`: tests `build_stream_message` output shape
- `test_verify_ws_token_rejects_missing_token`: asserts HTTP 401 on missing WS token

**Fake objects:** `FakePool`, `FakeDB`, `FakeApp`, `FakeState`, `FakeRequest`, `FakeWebSocket`

---

### `backend/tests/test_inference_isolation.py`

**Purpose:** Unit tests for per-camera state isolation in `InferencePipeline`.

**Tests:**
- `test_per_camera_runtime_state_isolated`: verifies that two `CameraRuntimeState` objects do not share state
- `test_load_camera_config_preserves_interaction_state`: verifies config reload doesn't replace the `interaction` object identity
- `test_load_camera_config_reconfigures_detector_without_replacing_it`: verifies hot-reconfigure updates `hand_dist_px` and `interaction_frames` in-place

**Dependencies:** `services.inference.ml.pipeline.InferencePipeline`, `unittest.mock.AsyncMock`, `numpy`

---

### `backend/tests/test_telegram_alert.py`

**Purpose:** Manual integration test / development script for testing Telegram bot connectivity. Not a pytest test (uses `asyncio.run(main())`). Auto-discovers chat IDs from `getUpdates`. Sends two test messages.

**Note:** Contains a hardcoded bot token in the fallback default — development artifact.

---

### `backend/tests/integration/test_e2e_latency.py`

**Purpose:** End-to-end latency measurement script. Writes synthetic frames to SHM, injects `FramePointer` into Redis Stream `frames_meta`, listens on `predictions` stream for matching `trace_id`. Reports p50/p95/p99 latency. Targets: p50 < 60ms, p95 < 100ms, p99 < 150ms.

**Note:** Uses `frames_meta` Redis Stream key — this differs from the actual production key `"frames"` (Redis list). This script appears to use a legacy interface (stream vs. list).

---

### `backend/tests/integration/test_video_pipeline.py`

**Purpose:** Manual integration test that feeds a video file through the pipeline via `RingBufferWriter` and Redis `"frames"` list. Listens on `detections:{camera_id}` pub/sub for responses. Measures per-frame round-trip latency.

**Note:** Listens on `detections:{camera_id}` — the production inference service publishes to `telemetry:{camera_id}`. Channel name mismatch; this would receive nothing in production.

---

### `backend/tests/inspect_data.py`

Development utility script (not a pytest test). Not read in detail.

---

## Backend — Infrastructure

### `backend/scripts/schema.sql`

**Purpose:** PostgreSQL DDL for the `detection_events` table.

**Table:** `detection_events`
- Partitioned by `RANGE (created_at)` (time-series partitioning)
- Primary key: `(id BIGSERIAL, created_at TIMESTAMPTZ)` (composite for partition compatibility)
- Key columns: event_id (TEXT, unique per created_at), camera_id, class_name, confidence, severity, event_type, trace_id, frame_ref (JSONB), detections (JSONB), metadata (JSONB), payload (JSONB), schema_version, evidence_uri, t_capture (BIGINT), t_output (BIGINT)
- Partitions: `detection_events_2026_03`, `detection_events_2026_04`
- Indexes: camera_id, created_at DESC, trace_id, unique (event_id, created_at)
- Also includes `ALTER TABLE ADD COLUMN IF NOT EXISTS` migrations for idempotent re-runs

---

### `backend/docker-compose.yml`

**Services:**

| Service | Image/Dockerfile | Ports | IPC |
|---|---|---|---|
| `redis` | redis:7-alpine | 6379 | — |
| `postgres` | postgres:16-alpine | 5433:5432 | — |
| `mqtt` | eclipse-mosquitto:2 | 1883 | — |
| `pgadmin` | dpage/pgadmin4:latest | 5050:80 | — |
| `signaling` | Dockerfile.signaling | 9000, 9100 | — |
| `mediabridge` | Dockerfile.mediabridge | 9102 | `host` |
| `inference` | Dockerfile.inference | 9101 | `host` (NVIDIA GPU, 1 device) |
| `alerting` | Dockerfile.alerting | 9103 | — |
| `persistence` | Dockerfile.persistence | 9104 | — |

**Volumes:** redis-data, pg-data, pgadmin-data, evidence-data, `./models:/app/models:ro` (inference)

**Note:** `mediabridge` and `inference` use `ipc: host` to share `/dev/shm` for the ring buffer. Inference requires NVIDIA GPU via `deploy.resources.reservations.devices`.

---

### Dockerfiles

All services use identical two-stage pattern:
1. **Builder** (`python:3.11-slim`): installs `uv`, runs `uv sync --frozen --no-dev --no-install-project`
2. **Runtime** (`python:3.11-slim`): copies `.venv` from builder, copies service-specific code and `shared/`

| Dockerfile | Extra APT packages | Entry CMD | User |
|---|---|---|---|
| `Dockerfile.signaling` | — | uvicorn :9000 | appuser |
| `Dockerfile.inference` | libgl1, libglib2.0-0, libsm6, libxext6 | python -m services.inference.main | root |
| `Dockerfile.mediabridge` | libgl1, libglib2.0-0, libsm6, libxext6 | python -m services.mediabridge.main | root |
| `Dockerfile.alerting` | — | python -m services.alerting.main | appuser |
| `Dockerfile.persistence` | — | python -m services.persistence.main | appuser |

---

## Frontend — App Pages

**Root:** `frontend/src/app/` (Next.js App Router)

---

### `frontend/src/app/layout.tsx`

**Purpose:** Root layout. Sets `dark` class on html, loads Fira Code + Fira Sans fonts from Google Fonts. Wraps all children in `QueryProvider` (TanStack Query).

**Metadata:** `title: "Antigravity Vision | AI Surveillance"`

---

### `frontend/src/app/page.tsx`

**Purpose:** Dashboard home (`/`). Displays grid of `StreamCard` components for each active camera. "Connect Camera" button opens `ConnectionModal`. Empty state when no cameras registered.

**State:** reads `cameras` from `useCameraStore`. Opens `ConnectionModal` via local `useState`.

**Dependencies:** `DashboardShell`, `ConnectionModal`, `StreamCard`, `useCameraStore`

---

### `frontend/src/app/cameras/page.tsx`

**Purpose:** Camera management page (`/cameras`). Currently a placeholder — displays "Enhanced Configuration Coming Soon". No functional content.

---

### `frontend/src/app/history/page.tsx`

**Purpose:** Forensic history page (`/history`). Fetches `GET /api/events` with TanStack Query. Renders a filtered/searchable table of incident events with confidence bar, severity badge, and action buttons (view/delete — buttons are UI-only, no actions implemented).

**Filters:** text search on camera_id and label; dropdown filter by label (all/shoplifting/weapon). Auto-logout on 401.

**Dependencies:** `DashboardShell`, `authHeaders`, `buildApiUrl`, `isAuthFailure`, `cn`, `useAuthStore`, `@tanstack/react-query`

---

### `frontend/src/app/settings/page.tsx`

**Purpose:** Settings page (`/settings`). Placeholder content — two disabled/stub card slots. No functional controls.

---

## Frontend — Components

**Root:** `frontend/src/components/`

---

### `frontend/src/components/auth/AuthPanel.tsx`

**Purpose:** Full-page login form. POSTs OAuth2 form to `/auth/token`. Stores returned `access_token` via `useAuthStore.setToken()`. Shows inline error on failure.

**Dependencies:** `buildApiUrl`, `cn`, `useAuthStore`

---

### `frontend/src/components/dashboard/ConnectionModal.tsx`

**Purpose:** Modal for connecting a new camera. Supports two modes: RTSP URL or local webcam. POSTs to `/api/camera/connect`. On success, calls `useCameraStore.addCamera()` with the returned stream ID.

**Mutation:** TanStack Query `useMutation` wrapping the POST. Handles auth failure by calling `logout()`.

**Dependencies:** `@tanstack/react-query`, `authHeaders`, `buildApiUrl`, `getAuthFailureMessage`, `isAuthFailure`, `cn`, `useAuthStore`, `useCameraStore`

---

### `frontend/src/components/dashboard/StreamCard.tsx`

**Purpose:** Live camera stream card. Opens WebSocket to `/ws/camera/{id}?token=...`. Renders JPEG frames via `<img>` tag (base64 src assignment). Overlays bounding boxes and incident banner on `<canvas>` via `drawDetections()`. Shows liveness indicator (pulse dot), incident status, fullscreen toggle.

**`drawDetections(detections, incident, canvas)`:** Canvas 2D API rendering. Persons get blue boxes with track ID; items get amber boxes. Incident shows red banner at top.

**State:** `isLive`, `isFullscreen`, `incident` (local useState). Closes WS on unmount.

**Dependencies:** `buildWsUrl`, `getAuthFailureMessage`, `cn`, `useAuthStore`

---

### `frontend/src/components/layout/DashboardShell.tsx`

**Purpose:** Main layout wrapper. On mount: calls `hydrate()` to restore auth from localStorage. Renders `AuthPanel` if unauthenticated. Renders sidebar + header + scrollable content area. Header shows backend status badge from `systemStatus`.

**Side effects:** mounts `useCamerasSynchronizer()` and `useSystemStatusWebSocket()` hooks.

**Dependencies:** `AuthPanel`, `Sidebar`, `useCamerasSynchronizer`, `useSystemStatusWebSocket`, `useAuthStore`, `useCameraStore`

---

### `frontend/src/components/layout/Sidebar.tsx`

**Purpose:** Left navigation sidebar. Three nav items: Dashboard (`/`), Cameras (`/cameras`), Persistence (`/history`). Bottom hardware status section showing GPU load, GPU temperature, VRAM (from `systemStatus` in `useCameraStore`). Active route highlighted.

**Dependencies:** `useCameraStore`, `lucide-react`, `next/link`, `next/navigation`, `cn`

---

### `frontend/src/components/providers/QueryProvider.tsx`

**Purpose:** TanStack Query context provider. Creates `QueryClient` with `staleTime: 60000ms`, `refetchOnWindowFocus: false`.

---

## Frontend — Hooks

**Root:** `frontend/src/hooks/`

---

### `frontend/src/hooks/useCamerasSynchronizer.ts`

**Purpose:** Polls `GET /api/cameras/` every 10 seconds (TanStack Query `refetchInterval`) and syncs the result into `useCameraStore.setCameras()`. Camera names are derived from IDs (uppercase, underscores replaced with spaces). Auto-logout on 401.

**Dependencies:** `@tanstack/react-query`, `authHeaders`, `buildApiUrl`, `isAuthFailure`, `useAuthStore`, `useCameraStore`

---

### `frontend/src/hooks/useSystemStatusWebSocket.ts`

**Purpose:** Opens WebSocket to `/ws/status?token=...`. Parses JSON messages and calls `setSystemStatus()` with GPU util/mem/temp and CPU/RAM. On close or error: sets `status: "degraded"` with zeros. Auto-logout on code 1008.

**Dependencies:** `buildWsUrl`, `getAuthFailureMessage`, `useAuthStore`, `useCameraStore`

---

### `frontend/src/hooks/useStatusPoller.ts`

**Purpose:** Polls `GET /api/status` using TanStack Query. Syncs result into `setSystemStatus`. **Currently disabled** (`enabled: false` in query options) — superseded by `useSystemStatusWebSocket`.

**Dependencies:** `@tanstack/react-query`, `authHeaders`, `buildApiUrl`, `useAuthStore`, `useCameraStore`

---

## Frontend — Stores

**Root:** `frontend/src/stores/`

---

### `frontend/src/stores/useAuthStore.ts`

**Purpose:** Zustand auth store. Manages JWT token with localStorage persistence and expiry validation.

**State:** `token: string | null`, `hydrated: boolean`

**Actions:**
- `setToken(token)`: validates expiry via `isTokenExpired()` before storing to localStorage
- `hydrate()`: reads token from localStorage on mount, validates expiry, sets `hydrated = true`
- `logout()`: clears localStorage and sets `token = null`

**Storage key:** `"pipeline_auth_token"`

**Dependencies:** `zustand`, `isTokenExpired` from `@/lib/auth`

---

### `frontend/src/stores/useCameraStore.ts`

**Purpose:** Zustand camera and system status store.

**State:**
- `cameras: Record<string, Camera>` — map of camera ID to Camera object (`id`, `name`, `url`, `status`, `lastDetection?`)
- `systemStatus: SystemStatus | null` — `status`, `gpu_util`, `gpu_mem`, `gpu_temp`, `cpu_usage`, `ram_usage`
- `logs: string[]` — last 100 log entries

**Actions:** `setSystemStatus`, `setCameras`, `updateCamera`, `addCamera`, `removeCamera`, `addLog`

**Dependencies:** `zustand`

---

## Frontend — Lib Utilities

**Root:** `frontend/src/lib/`

---

### `frontend/src/lib/api.ts`

**Purpose:** API base URL configuration and helper functions.

**Config:** `NEXT_PUBLIC_API_BASE_URL` (default: `"http://localhost:9001"`)

**Exports:**
- `getApiBaseUrl()` → base URL string
- `getWsBaseUrl()` → replaces `http` with `ws` in base URL
- `buildApiUrl(path)` → `${API_BASE_URL}${path}`
- `buildWsUrl(path, token?)` → URL object with optional `?token=` query param
- `authHeaders(options) -> Headers` → sets `Authorization: Bearer {token}` header

---

### `frontend/src/lib/auth.ts`

**Purpose:** JWT client-side validation utilities.

**Exports:**
- `getTokenPayload(token) -> JwtPayload | null`: decodes base64url JWT payload (browser `atob`)
- `isTokenExpired(token) -> bool`: checks `exp` claim against `Date.now()`
- `isAuthFailure(status, detail?) -> bool`: true if status 401 or detail contains "token"
- `getAuthFailureMessage() -> string`: returns `"Session expired. Sign in again."`

---

### `frontend/src/lib/cn.ts`

**Purpose:** Minimal class name joiner.

`cn(...classes)`: filters falsy values and joins with space. Minimal alternative to `clsx` + `tailwind-merge` (both are installed but `cn` is custom).

---

## Data Flow & Message Contracts

### Frame Ingestion → Inference

```
Camera (RTSP/Webcam)
    → MediaBridge.CameraWorker.run()
    → SHMWriter.write(frame)                  [SHM: cam_{id}_ring, _idx, _gen]
    → redis.rpush("frames", FramePointer JSON)
    → redis.set(f"frame_ptr:{camera_id}", FramePointer JSON)

Inference.main._inference_worker()
    → redis.blpop("frames")
    → InferencePipeline.process(payload, redis)
        → ReaderCache.get_reader(camera_id, ...).read(slot_id, generation)
        → ObjectDetector.detect_and_track(frame)
        → ItemInteractionDetector.update(tracks, items)
        → TemporalBuffer.push(frame)
        [if should_classify and no active task:]
            → BehaviorClassifier.classify(clip)  [async task]
            → IncidentEvent → redis.xadd("stream:incidents")
            → redis.publish(f"incidents:{camera_id}")
        → FrameTelemetryMessage → redis.publish(f"telemetry:{camera_id}")
        → redis.set(f"telemetry:latest:{camera_id}")
```

### Incident Dispatch

```
Redis Stream "stream:incidents"
    → Alerting.main.run()        [consumer group: alerting_group]
        → TelegramService.send_shoplifting_alert()
        → MQTTService.publish()   [stub]
        → redis.xack()

    → Persistence.main.run()     [consumer group: persistence_group]
        → DBWriter.save_event()
        → asyncpg INSERT detection_events
        → redis.xack()
```

### Frontend Real-Time Stream

```
Frontend StreamCard
    → WebSocket /ws/camera/{id}?token=
    → Signaling.ws.camera_stream.ws_camera()
        → grab_jpeg() + grab_metadata() [every 1/fps seconds]
        → build_stream_message() → CameraStreamMessage JSON
        → WebSocket send_text()
```

### Frontend Predictions / Incidents

```
Frontend (future: /ws/predictions)
    → WebSocket /ws/predictions?token=
    → Signaling.ws.predictions.ws_predictions()
        → redis.psubscribe("telemetry:*", "incidents:*")
        → forward pmessage to WebSocket
```

---

## Redis Key Space

| Key Pattern | Type | Written by | Read by | Description |
|---|---|---|---|---|
| `frames` | List | MediaBridge | Inference | `FramePointer` JSON queue. Inference `blpop`s. |
| `frame_ptr:{camera_id}` | String | MediaBridge | Signaling, Inference | Latest `FramePointer` for snapshot/stream |
| `camera_sources` | Hash | Signaling (POST /camera/connect, DELETE /cameras/{id}) | MediaBridge | `{camera_id: source_url}` |
| `camera_status:{camera_id}` | String | MediaBridge | (monitoring) | `online` / `reconnecting` / `offline` |
| `config:{camera_id}` | Hash | Signaling (PUT /api/config/{id}), Signaling (POST /camera/connect) | Inference | Per-camera ROI+threshold config |
| `telemetry:{camera_id}` | Pub/Sub channel | Inference | Signaling WS /ws/predictions | Live `FrameTelemetryMessage` JSON |
| `telemetry:latest:{camera_id}` | String | Inference | Signaling /ws/camera, /api/camera/snapshot | Latest telemetry snapshot |
| `incidents:{camera_id}` | Pub/Sub channel | Inference, Signaling (/api/alerts/trigger) | Signaling WS /ws/predictions | Live `IncidentEvent` JSON |
| `stream:incidents` | Stream | Inference, Signaling (/api/alerts/trigger) | Alerting, Persistence | Canonical incident events |
| `reid:embeddings:{global_id}` | String (bytes) | Inference ReIDService | Inference ReIDService | Person appearance embedding (float32 bytes, TTL 3600s) |
| `logs` | Pub/Sub channel | All services (RedisLogHandler) | Signaling WS /ws/logs | Structured JSON log records |

---

## Prometheus Metrics Ports

| Service | Port | Notable metrics |
|---|---|---|
| Signaling | 9100 (via `/metrics` ASGI mount) | FastAPI request metrics |
| Inference | 9101 | inference_latency_seconds, frames_processed, frames_dropped, gpu_memory_bytes |
| MediaBridge | 9102 | frames_captured, frames_dropped, cameras_active, capture_latency_ms |
| Alerting | 9103 | alerts_sent_total |
| Persistence | 9104 | db_write_latency_seconds |

---

## Environment Variables

All variables are read by `backend/shared/core/settings.py` unless noted.

| Variable | Service | Default | Description |
|---|---|---|---|
| `REDIS_HOST` | All | `localhost` | Redis hostname |
| `REDIS_PORT` | All | `6379` | Redis port |
| `REDIS_PASSWORD` | All | `""` | Redis auth password |
| `REDIS_DB` | All | `0` | Redis database index |
| `REDIS_URL` | All | `""` | Override full Redis URL |
| `POSTGRES_HOST` | Signaling, Persistence | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | Signaling, Persistence | `5432` | PostgreSQL port |
| `POSTGRES_DB` | Signaling, Persistence | `pipeline_events` | Database name |
| `POSTGRES_USER` | Signaling, Persistence | `pipeline_user` | Database user |
| `POSTGRES_PASSWORD` | Signaling, Persistence | `""` | Database password |
| `POSTGRES_POOL_SIZE` | Signaling, Persistence | `10` | Max asyncpg pool connections |
| `TELEGRAM_BOT_TOKEN` | Alerting | `""` | Telegram Bot API token |
| `TELEGRAM_ADMIN_CHAT_IDS` | Alerting | `""` | Comma-separated chat IDs |
| `JWT_SECRET` | Signaling | `""` | JWT HMAC signing key |
| `JWT_ALGORITHM` | Signaling | `HS256` | JWT algorithm |
| `JWT_EXPIRE_MINUTES` | Signaling | `60` | Token expiry in minutes |
| `ADMIN_USERNAME` | Signaling | `""` | Admin login username |
| `ADMIN_PASSWORD` | Signaling | `""` | Admin login password |
| `CORS_ORIGINS` | Signaling | `http://localhost:3000,...` | Comma-separated allowed origins |
| `SHM_SLOTS_PER_CAM` | MediaBridge, Inference, Signaling | `32` | Ring buffer depth per camera |
| `FRAME_WIDTH` | MediaBridge, Inference, Signaling | `1280` | Canonical frame width |
| `FRAME_HEIGHT` | MediaBridge, Inference, Signaling | `720` | Canonical frame height |
| `FRAME_QUEUE_MAXLEN` | MediaBridge | `256` | Max Redis `frames` list length |
| `CAMERA_STREAM_FPS` | MediaBridge, Signaling | `15` | Target stream FPS |
| `DETECTOR_ENGINE_PATH` | Inference | `models/yolo/yolo26n.engine` | TensorRT detector path |
| `CLASSIFIER_ENGINE_PATH` | Inference | `models/shoplifting/cnn_transformer.engine` | TensorRT classifier path |
| `TEMPORAL_WINDOW` | Inference | `16` | Behavior clip length (frames) |
| `DEFAULT_CONFIDENCE_THRESHOLD` | Inference | `0.7` | Detection confidence filter |
| `HAND_DIST_PX` | Inference | `80` | Hand-item proximity threshold |
| `INTERACTION_FRAMES` | Inference | `5` | Consecutive frames to trigger |
| `ALERT_CONFIDENCE_THRESHOLD` | Alerting, Inference | `0.8` | Min confidence for alert dispatch |
| `APP_ENV` | Signaling | `development` | Environment name (affects CORS/security validation) |
| `CONFIG_POLL_INTERVAL_S` | Inference | `5` | Seconds between config re-reads |
| `ENABLE_REDIS_LOGS` | All | `true` | Enable Redis log publishing |
| `INFERENCE_GPU_WORKERS` | Inference | `1` | Number of GPU worker coroutines |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend | `http://localhost:9001` | Signaling API base URL |

---

*End of structural map.*
