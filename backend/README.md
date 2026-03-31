# RTSP Camera Backend

FastAPI backend for a real-time CCTV system built around MediaMTX, PyAV workers, PostgreSQL, WebSocket updates, Prometheus/Grafana observability, and backend-native person tracking with Deep SORT + Milvus identity matching.

This backend is the control plane and backend-processing plane for the system. Browsers do not connect to RTSP directly. Media is distributed through MediaMTX, stream lifecycle is managed by FastAPI, and backend workers consume MediaMTX RTSP pull paths for sampling and tracking.

## What This Backend Does

- manages RTSP camera inventory
- validates camera reachability
- generates and synchronizes MediaMTX path config
- exposes WebRTC as primary playback and HLS as fallback
- runs PyAV frame workers for sampled backend processing
- runs annotated tracking workers for person detection and ID assignment
- assigns persistent cross-camera identities with Milvus
- republishes an annotated tracked stream back into MediaMTX
- stores camera and stream state in PostgreSQL
- pushes live lifecycle and tracking updates over WebSocket
- publishes tracking metadata snapshots to Kafka
- exposes Prometheus metrics and ships Grafana dashboards
- optionally consumes Kafka lifecycle / AI topics

## Architecture

The system is intentionally split into separate planes.

- Control plane: FastAPI + PostgreSQL + WebSocket + optional Kafka
- Media plane: MediaMTX
- Backend processing plane: PyAV workers and tracking workers
- Observability plane: Prometheus + Grafana

### High-Level Flow

```mermaid
flowchart LR
    Camera["RTSP Camera"]
    MediaMTX["MediaMTX\nRTSP ingest + WebRTC + HLS"]
    API["FastAPI Backend"]
    PyAV["PyAV Frame Worker"]
    Tracking["Tracking Worker\nYOLO26 + Deep SORT + Milvus"]
    Annotated["Annotated Stream\n<stream>_tracked"]
    Frontend["Frontend"]
    DB["PostgreSQL"]
    WS["WebSocket"]
    Kafka["Kafka"]
    Metrics["Prometheus + Grafana"]

    Camera --> MediaMTX
    MediaMTX --> Frontend
    MediaMTX --> PyAV
    MediaMTX --> Tracking
    Tracking --> MediaMTX
    MediaMTX --> Annotated
    API --> DB
    API --> WS
    Kafka --> API
    API --> Metrics
    PyAV --> Metrics
    Tracking --> Metrics
    Frontend -->|REST| API
    Frontend -->|WS| API
    Frontend -->|WHEP / HLS| MediaMTX
```

### Active Stream Lifecycle

```text
Camera RTSP
-> MediaMTX path
-> WebRTC/HLS playback for frontend
-> RTSP pull URL for backend workers
```

### Active Tracking Lifecycle

```text
MediaMTX RTSP pull
-> Tracking worker
-> YOLO26 person detection
-> Deep SORT local track assignment
-> Milvus identity match / reuse
-> annotated frame rendering
-> FFmpeg RTSP publish
-> MediaMTX annotated path <stream_name>_tracked
-> WebRTC/HLS playback for tracked output
```

## Current Runtime Model

### MediaMTX

MediaMTX is the media router:

- pulls from camera RTSP sources on demand
- serves WebRTC through WHEP
- serves low-latency HLS
- exposes RTSP pull URLs for backend workers
- exposes a Control API for runtime path sync

The backend no longer relies on a static hand-maintained `mediamtx.yml`. It renders:

- `runtime/mediamtx.generated.yml`

and then reconciles runtime paths through the MediaMTX Control API.

### PyAV Frame Workers

The standard realtime worker path lives under:

- [frame_worker.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/frame_worker.py)
- [stream_manager.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/stream_manager.py)

These workers:

- connect to `rtsp://localhost:8554/<stream_name>`
- sample frames at a bounded FPS
- publish sampled metadata to the shared queue
- record metrics like FPS, queue latency, decode time, reconnect attempts

### Tracking Workers

The tracking path lives under:

- [worker.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/worker.py)
- [manager.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/manager.py)
- [yolo26_detector.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/detectors/yolo26_detector.py)
- [milvus_store.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/identity/milvus_store.py)

These workers:

- decode from the raw MediaMTX path
- detect persons with the existing YOLO26 ONNX model
- embed persons with the vendored Deep SORT mobilenet embedder
- match or create persistent identities in Milvus
- draw boxes + IDs
- publish an annotated RTSP stream back into MediaMTX
- fan out track metadata through WebSocket and Kafka

### Persistent Identity Store

The tracking pipeline uses Milvus for cross-camera identity persistence.

Default runtime behavior:

- local persistent store via Milvus Lite
- default DB file:
  - `runtime/milvus_tracking.db`

You can also point the backend at a remote Milvus deployment by overriding the tracking store URI and token.

### PostgreSQL

PostgreSQL stores:

- camera metadata
- camera validation state
- stream lifecycle state
- stream playback metadata
- stream error and reconnect counters

### WebSocket

The backend publishes:

- initial stream snapshot
- stream lifecycle updates
- stream-connected events
- tracking updates

The frontend should treat backend REST + WebSocket as the source of truth for lifecycle state. WebRTC/HLS is playback only.

## Main Backend Modules

### Bootstrap

- [main.py](/home/karthik/Downloads/pipeline_opencv/backend/src/main.py)
  - builds the application container
  - opens the DB pool
  - syncs MediaMTX config on startup
  - starts metrics
  - starts Kafka consumer
  - starts tracking-capable services

### Camera Domain

- [camera_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/camera/camera_service.py)
- [camera_repository.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/camera/camera_repository.py)
- [camera_validator.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/camera/camera_validator.py)

Responsibilities:

- CRUD
- RTSP validation
- MediaMTX config regeneration after create/update/delete

### Stream Domain

- [stream_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/stream/stream_service.py)
- [stream_repository.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/stream/stream_repository.py)
- [kafka_event_consumer.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/stream/kafka_event_consumer.py)

Responsibilities:

- start / stop / status / info
- persistence of stream lifecycle state
- websocket event rebuild from Kafka payloads

### MediaMTX Integration

- [mediamtx_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/mediamtx_service.py)
- [mediamtx_control_api.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/mediamtx_control_api.py)
- [mediamtx.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/mediamtx.py)

Responsibilities:

- render generated config
- manage local MediaMTX process when enabled
- validate external MediaMTX readiness
- reconcile paths through the Control API
- derive raw and tracked stream endpoints

### Tracking

- [manager.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/manager.py)
- [worker.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/worker.py)
- [updates.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/updates.py)
- [yolo26_detector.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/detectors/yolo26_detector.py)
- [milvus_store.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/identity/milvus_store.py)

### Tracking Kafka

- [service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking_kafka/service.py)
- [publisher.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking_kafka/publisher.py)
- [tracking_events.py](/home/karthik/Downloads/pipeline_opencv/backend/src/schemas/tracking_events.py)

Responsibilities:

- person detection
- persistent identity matching
- annotated tracked-stream publishing
- tracking websocket updates
- Kafka tracking snapshot publishing keyed by `camera_id`

### Presentation

- [stream_contract_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/presentation/stream_contract_service.py)
- [websocket_manager.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/presentation/websocket_manager.py)

Responsibilities:

- build frontend-ready stream contracts
- fan out websocket events

### Observability

- [metrics.py](/home/karthik/Downloads/pipeline_opencv/backend/src/observability/metrics.py)
- [metrics_server.py](/home/karthik/Downloads/pipeline_opencv/backend/src/observability/metrics_server.py)
- [system_metrics.py](/home/karthik/Downloads/pipeline_opencv/backend/src/observability/system_metrics.py)

## Project Layout

```text
backend/
├── docker-compose.yaml
├── docs/
├── model_repository/
│   ├── cnn_transformers/
│   ├── hf_vjepa2_finetune/
│   └── yolo/
├── observability/
│   ├── grafana/
│   └── prometheus/
├── runtime/
│   ├── mediamtx.generated.yml
│   └── milvus_tracking.db
├── scripts/
│   ├── migrations/
│   └── sql/
├── src/
│   ├── core/
│   ├── models/
│   ├── observability/
│   ├── routes/
│   ├── schemas/
│   ├── services/
│   │   ├── camera/
│   │   ├── deep_sort_realtime/
│   │   ├── presentation/
│   │   ├── realtime_video/
│   │   ├── tracking/
│   │   ├── tracking_kafka/
│   │   └── stream/
│   └── utils/
└── tests/
```

## Camera Model

Each camera can be registered in one of two ways:

1. `direct_rtsp_url`
2. `host + port + path + credentials`

Important fields:

- `id`
- `name`
- `location`
- `direct_rtsp_url`
- `host`
- `port`
- `path`
- `transport`
- `status`
- `metadata`
- `tags`
- `last_validation_status`
- `stream_status`

`metadata["mediamtx_stream_name"]` can override the default MediaMTX path. If omitted, the backend uses a normalized `camera_id`.

## Stream State Model

### Camera status

- `active`
- `inactive`
- `error`

### Validation status

- `unknown`
- `reachable`
- `unreachable`

### Stream status

- `stopped`
- `starting`
- `running`
- `stopping`
- `reconnecting`
- `error`
- `crashed`

### Stream protocol

- `webrtc`
- `hls`

## API Overview

All HTTP endpoints return the same envelope:

```json
{
  "status": "success",
  "message": "Human-readable message",
  "data": {},
  "error_code": null,
  "timestamp": "2026-04-01T00:00:00Z",
  "meta": null
}
```

### Camera endpoints

- `POST /cameras`
- `GET /cameras`
- `GET /cameras/{camera_id}`
- `PUT /cameras/{camera_id}`
- `DELETE /cameras/{camera_id}`
- `POST /cameras/{camera_id}/validate`

### Stream endpoints

- `POST /streams/{camera_id}/start`
- `POST /streams/{camera_id}/stop`
- `GET /streams/{camera_id}/status`
- `GET /streams/{camera_id}/info`
- `WS /streams/ws/updates`

### Health endpoints

- `GET /health`
- `GET /health/db`
- `GET /health/stream/{camera_id}`

Interactive docs:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

## Stream Contract

`GET /streams/{camera_id}/info` and the start/stop/status APIs return a frontend-ready contract.

Example:

```json
{
  "camera_id": "cam_46cbe8bbfe55",
  "camera_name": "Gate 1",
  "stream_id": "stream_cam_46cbe8bbfe55",
  "stream_name": "cam_46cbe8bbfe55",
  "stream_identifier": "cam_46cbe8bbfe55:stream_cam_46cbe8bbfe55",
  "status": "running",
  "protocol": "webrtc",
  "playback_url": "http://localhost:8889/cam_46cbe8bbfe55/whep",
  "access_urls": {
    "webrtc_url": "http://localhost:8889/cam_46cbe8bbfe55/whep",
    "hls_url": "http://localhost:8888/cam_46cbe8bbfe55/index.m3u8",
    "rtsp_pull_url": "rtsp://localhost:8554/cam_46cbe8bbfe55"
  },
  "websocket_url": "ws://localhost:8000/streams/ws/updates",
  "tracking": {
    "enabled": true,
    "stream_name": "cam_46cbe8bbfe55_tracked",
    "access_urls": {
      "webrtc_url": "http://localhost:8889/cam_46cbe8bbfe55_tracked/whep",
      "hls_url": "http://localhost:8888/cam_46cbe8bbfe55_tracked/index.m3u8",
      "rtsp_pull_url": "rtsp://localhost:8554/cam_46cbe8bbfe55_tracked"
    },
    "is_registered": true,
    "is_process_alive": true,
    "reconnect_attempts": 0,
    "active_tracks": 2,
    "identity_backend": "milvus",
    "tracks": []
  },
  "worker": {
    "desired_state": "running",
    "is_registered": true,
    "is_process_alive": true,
    "restart_count": 0,
    "reconnect_attempts": 0,
    "sampled_frames": 0,
    "dropped_frames": 0,
    "current_fps": 0.0,
    "queue_latency_ms": 0.0,
    "decode_time_ms": 0.0
  }
}
```

Important notes:

- `playback_url` is the primary raw playback URL
- `access_urls.rtsp_pull_url` is for backend workers, not the browser
- `tracking.access_urls.*` points to the annotated tracked output
- `worker` is live in-memory worker state
- `tracking` is live tracking worker state

## WebSocket Contract

WebSocket endpoint:

```text
ws://localhost:8000/streams/ws/updates
```

Optional camera filter:

```text
ws://localhost:8000/streams/ws/updates?camera_id=<camera_id>
```

Typical event types:

- `stream.snapshot`
- `stream.updated`
- `stream.connected`
- `tracking.updated`

The server sends an initial snapshot on connect, then pushes event-driven updates.

## Tracking Pipeline

### Detector

The backend uses the existing YOLO26 asset already present in the repo:

- [yolo26n.onnx](/home/karthik/Downloads/pipeline_opencv/backend/model_repository/yolo/yolo26n.onnx)

Current runtime choice:

- OpenCV DNN + ONNX

The `.engine` file is not the active runtime path right now because TensorRT runtime is not part of this backend environment.

### Tracker

The backend uses the vendored Deep SORT implementation under:

- [deepsort_tracker.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/deep_sort_realtime/deepsort_tracker.py)

Embedder weights:

- [mobilenetv2_bottleneck_wts.pt](/home/karthik/Downloads/pipeline_opencv/backend/src/services/deep_sort_realtime/embedder/weights/mobilenetv2_bottleneck_wts.pt)

### Identity Matching

Persistent identity matching is handled by Milvus:

- same person seen again in the same or another camera can reuse the same persistent ID
- local Deep SORT track IDs remain per-worker / per-session
- persistent IDs represent cross-camera identity memory

### Annotated Output

For a raw stream:

```text
cam_123
```

the tracked stream becomes:

```text
cam_123_tracked
```

That annotated stream is published back into MediaMTX and automatically gains:

- WebRTC WHEP URL
- HLS URL
- RTSP pull URL

## MediaMTX Integration

### Generated config

The backend renders:

- `runtime/mediamtx.generated.yml`

This file contains:

- auth config
- API + metrics listeners
- RTSP / HLS / WebRTC listeners
- default path behavior
- camera source paths

### Runtime sync

For external MediaMTX mode:

- backend writes the generated file
- backend authenticates to the MediaMTX Control API
- backend reconciles path state without requiring a restart per camera create/update/delete

### Control API auth

Important variables:

- `MEDIAMTX_API_USERNAME`
- `MEDIAMTX_API_PASSWORD`

Keep them in deployment secrets for production. The backend and MediaMTX must agree on the same credentials.

### External vs managed mode

Supported modes:

1. External MediaMTX
   - `MEDIAMTX_MANAGE_PROCESS=false`
   - preferred for Docker / deployment

2. Backend-managed MediaMTX
   - `MEDIAMTX_MANAGE_PROCESS=true`
   - backend starts `mediamtx` directly

The current `docker-compose.yaml` uses external MediaMTX.

## Database Schema

Tables:

- `cameras`
- `stream_state`
- `schema_migrations`

Migrations:

- [001_create_camera_table.sql](/home/karthik/Downloads/pipeline_opencv/backend/scripts/migrations/001_create_camera_table.sql)
- [002_create_stream_table.sql](/home/karthik/Downloads/pipeline_opencv/backend/scripts/migrations/002_create_stream_table.sql)
- [003_allow_webrtc_stream_protocol.sql](/home/karthik/Downloads/pipeline_opencv/backend/scripts/migrations/003_allow_webrtc_stream_protocol.sql)

SQL layout:

- `scripts/sql/camera`
- `scripts/sql/stream`
- `scripts/sql/common`

## Configuration

Runtime settings live in:

- [config.py](/home/karthik/Downloads/pipeline_opencv/backend/src/core/config.py)

### Required

- `database_url`

### Core MediaMTX

- `MEDIAMTX_MANAGE_PROCESS`
- `MEDIAMTX_BINARY`
- `MEDIAMTX_GENERATED_CONFIG_PATH`
- `MEDIAMTX_API_BASE_URL`
- `MEDIAMTX_API_TIMEOUT_SECONDS`
- `MEDIAMTX_API_READY_TIMEOUT_SECONDS`
- `MEDIAMTX_API_USERNAME`
- `MEDIAMTX_API_PASSWORD`
- `MEDIAMTX_RTSP_BASE_URL`
- `MEDIAMTX_HLS_BASE_URL`
- `MEDIAMTX_WEBRTC_BASE_URL`

### Realtime frame workers

- `REALTIME_FRAME_SAMPLE_FPS`
- `REALTIME_FRAME_QUEUE_SIZE`
- `REALTIME_MAX_RECONNECT_ATTEMPTS`

### Tracking

- `TRACKING_ENABLED_BY_DEFAULT`
- `TRACKING_SAMPLE_FPS`
- `TRACKING_OUTPUT_FPS`
- `TRACKING_DETECTOR_MODEL_PATH`
- `TRACKING_DETECTOR_INPUT_SIZE`
- `TRACKING_DETECTOR_CONFIDENCE_THRESHOLD`
- `TRACKING_DETECTOR_IOU_THRESHOLD`
- `TRACKING_EMBEDDER_NAME`
- `TRACKING_EMBEDDER_WEIGHTS_PATH`
- `TRACKING_IDENTITY_STORE_URI`
- `TRACKING_IDENTITY_STORE_TOKEN`
- `TRACKING_IDENTITY_COLLECTION_NAME`
- `TRACKING_IDENTITY_DIMENSION`
- `TRACKING_IDENTITY_SIMILARITY_THRESHOLD`
- `TRACKING_IDENTITY_SEARCH_LIMIT`
- `TRACKING_IDENTITY_SYNC_INTERVAL_SECONDS`
- `TRACKING_PUBLISH_UPDATE_INTERVAL_SECONDS`
- `TRACKING_STREAM_SUFFIX`

### Public URLs

- `PUBLIC_API_BASE_URL`
- `PUBLIC_WS_BASE_URL`

### Observability

- `METRICS_ENABLED`
- `METRICS_HOST`
- `METRICS_PORT`
- `METRICS_COLLECTION_INTERVAL_SECONDS`

### Kafka

- `KAFKA_ENABLED`
- `KAFKA_BOOTSTRAP_SERVERS`
- `KAFKA_GROUP_ID`
- `KAFKA_CLIENT_ID`
- `KAFKA_TOPIC_CAMERA_STATUS`
- `KAFKA_TOPIC_CAMERA_EVENTS`
- `KAFKA_TOPIC_CAMERA_AI_RESULTS`
- `KAFKA_TOPIC_CAMERA_TRACKING_UPDATES`

## Local Development

### 1. Create the virtual environment

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
python -m venv .venv
.venv/bin/python -m pip install -e .[dev]
```

### 2. Configure `.env`

Current local example:

```env
database_url=postgresql://postgres:postgres@localhost:5432/postgres
MEDIAMTX_BINARY=mediamtx
MEDIAMTX_MANAGE_PROCESS=false
MEDIAMTX_API_USERNAME=backend-control
MEDIAMTX_API_PASSWORD=replace-with-a-real-secret
PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

### 3. Start infrastructure

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
docker compose up -d mediamtx kafka kafka-init prometheus grafana
```

Notes:

- PostgreSQL is required but is not provisioned in `docker-compose.yaml`
- point `database_url` to an existing PostgreSQL instance
- Milvus Lite is embedded in the backend process by default, so you do not need a separate Milvus container for local development unless you want one

### 4. Run migrations

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
.venv/bin/python -m src.utils.migration_runner
```

### 5. Start the API

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
.venv/bin/uvicorn src.main:app --reload
```

## Typical Usage

### Create a camera

```bash
curl -X POST http://127.0.0.1:8000/cameras \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Gate 1",
    "location": "Building 4",
    "direct_rtsp_url": "rtsp://192.168.1.2:8080/h264_ulaw.sdp",
    "transport": "tcp",
    "status": "active",
    "metadata": {
      "mediamtx_stream_name": "gate-1"
    }
  }'
```

### Validate a camera

```bash
curl -X POST http://127.0.0.1:8000/cameras/<camera_id>/validate
```

### Start a raw stream with tracking enabled

```bash
curl -X POST http://127.0.0.1:8000/streams/<camera_id>/start \
  -H 'Content-Type: application/json' \
  -d '{
    "requested_protocol": "webrtc",
    "sample_fps": 5,
    "force_restart": false,
    "enable_tracking_events": true
  }'
```

### Fetch the stream contract

```bash
curl http://127.0.0.1:8000/streams/<camera_id>/info
```

## Observability

### Backend metrics endpoint

```text
http://127.0.0.1:9109/metrics
```

Metrics include:

- frame counters
- frame latency histogram
- queue depth
- CPU / memory / network

### Local dashboard stack

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001`

Grafana credentials:

- username: `admin`
- password: `admin`

Observability assets:

- [observability/prometheus](/home/karthik/Downloads/pipeline_opencv/backend/observability/prometheus)
- [observability/grafana](/home/karthik/Downloads/pipeline_opencv/backend/observability/grafana)

## Testing and Quality

Run the backend checks with:

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
.venv/bin/python -m ruff check src tests
.venv/bin/python -m pytest
.venv/bin/python -m pylint src tests
```

The backend is maintained with strict linting and a `pylint` fail-under of `10`.

## Deployment Notes

### MediaMTX Control API credentials

For production:

- set `MEDIAMTX_API_USERNAME`
- set `MEDIAMTX_API_PASSWORD`
- make sure MediaMTX starts with the same auth values

Do not rely on ad hoc manual restarts for path sync. The backend is built to reconcile runtime paths through the Control API.

### Milvus runtime choice

Default:

- local Milvus Lite file

For larger deployments:

- point `TRACKING_IDENTITY_STORE_URI` at a remote Milvus service
- optionally set `TRACKING_IDENTITY_STORE_TOKEN`

### Setuptools compatibility

Milvus Lite currently still imports `pkg_resources`, so this backend pins:

- `setuptools<82`

That is intentional and should be preserved in deployment images until the upstream dependency removes that requirement.

### Browser behavior

- browsers never connect to RTSP directly
- WebRTC is the primary playback path
- HLS is fallback only
- WebSocket carries lifecycle and tracking updates, not media

## Legacy Modules

Older modules still exist in the repository from the previous worker design, especially under `src/services/stream`, but the active browser-playback architecture is:

```text
Camera
-> MediaMTX
-> WebRTC/HLS -> Frontend
-> RTSP pull -> PyAV worker
-> RTSP pull -> Tracking worker -> MediaMTX tracked stream
```

`wwwroot` is not part of the active backend tracking path anymore.
