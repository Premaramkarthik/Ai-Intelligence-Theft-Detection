# RTSP Camera Backend

FastAPI backend for camera management, MediaMTX stream distribution, PyAV frame sampling, PostgreSQL persistence, WebSocket status updates, and Prometheus-based observability.

This backend is the control plane for the CCTV system. It does not send RTSP directly to browsers. Instead, it manages camera metadata, stream lifecycle, MediaMTX path configuration, realtime worker state, and frontend-ready playback contracts.

## What This Backend Does

- Registers and manages RTSP cameras
- Validates RTSP connectivity before or after camera onboarding
- Generates and synchronizes MediaMTX path configuration
- Exposes WebRTC as the primary playback path and HLS as fallback
- Runs PyAV-based realtime workers that sample frames from MediaMTX RTSP pull URLs
- Persists stream lifecycle state in PostgreSQL
- Pushes live stream updates over WebSocket
- Exposes Prometheus metrics and ships Grafana/Prometheus local observability assets
- Optionally consumes Kafka lifecycle events for stream-state propagation

## Core Architecture

The system is intentionally split into separate planes:

- Control plane: FastAPI, PostgreSQL, WebSocket, optional Kafka
- Media plane: MediaMTX
- Frame extraction plane: PyAV workers pulling from MediaMTX
- Observability plane: Prometheus metrics + Grafana dashboards

### High-Level Diagram

```mermaid
flowchart LR
    Camera["RTSP Camera"]
    MediaMTX["MediaMTX\nRTSP ingest + WebRTC + HLS"]
    Frontend["Frontend\nDashboard + Player"]
    FastAPI["FastAPI\nControl Plane"]
    PyAV["PyAV Workers\nSampled frame extraction"]
    Queue["Bounded Async Queue"]
    Postgres["PostgreSQL"]
    Kafka["Kafka\nOptional events"]
    Metrics["Prometheus\n+ Grafana"]

    Camera --> MediaMTX
    MediaMTX --> Frontend
    MediaMTX --> PyAV
    PyAV --> Queue
    Frontend -->|REST| FastAPI
    Frontend -->|WebSocket| FastAPI
    FastAPI --> Postgres
    Kafka --> FastAPI
    FastAPI --> Metrics
    PyAV --> Metrics
```

### Stream Startup Flow

```mermaid
sequenceDiagram
    participant UI as Frontend
    participant API as FastAPI
    participant DB as PostgreSQL
    participant MM as MediaMTX
    participant Worker as PyAV Worker

    UI->>API: POST /streams/{camera_id}/start
    API->>DB: load camera + current stream state
    API->>MM: sync or verify MediaMTX path through Control API
    API->>DB: upsert requested stream state
    API->>Worker: start sampled frame worker
    Worker->>MM: pull rtsp://localhost:8554/{stream_name}
    API-->>UI: WebRTC URL + HLS URL + WebSocket URL
    UI->>MM: open WHEP URL
    UI->>API: connect /streams/ws/updates
```

## Runtime Model

### MediaMTX

MediaMTX is the media distribution layer:

- pulls RTSP from cameras on demand
- serves WebRTC for low-latency browser playback
- serves low-latency HLS as fallback
- exposes a Control API for runtime path management

The backend does not use FFmpeg subprocesses as the primary playback path anymore. MediaMTX owns distribution. The backend only manages configuration and consumes MediaMTX outputs.

### PyAV Workers

PyAV workers are used only for backend frame extraction and future AI-ready processing:

- workers connect to MediaMTX RTSP pull URLs, not camera RTSP URLs directly
- frames are sampled at a configurable FPS
- sampled frames enter a bounded in-memory queue
- worker metrics include sampled frames, dropped frames, reconnect attempts, FPS, queue latency, and decode latency

### PostgreSQL

PostgreSQL stores:

- camera metadata
- validation status
- current stream lifecycle state
- stream errors and reconnect counters
- migration history

### WebSocket

The backend provides a WebSocket endpoint for realtime stream status:

- initial snapshot on connect
- incremental lifecycle updates
- connection notifications when sampled frames start flowing

The frontend should treat WebSocket as the source of truth for stream lifecycle state. WebRTC is playback only.

## Main Backend Modules

### Application bootstrap

- `src/main.py`
  - creates the FastAPI app
  - opens the database pool
  - starts Prometheus metrics
  - starts the system metrics collector
  - builds the dependency container
  - syncs MediaMTX config on boot
  - starts the Kafka consumer

### Camera domain

- `src/services/camera/camera_service.py`
  - camera CRUD
  - camera validation orchestration
  - automatic MediaMTX config refresh after create, update, and delete

- `src/services/camera/camera_repository.py`
  - SQL-backed camera persistence

- `src/services/camera/camera_validator.py`
  - validation of RTSP reachability

### Stream domain

- `src/services/stream/stream_service.py`
  - start, stop, status, info, health
  - stream contract generation
  - stream event application

- `src/services/stream/stream_repository.py`
  - persistence for `stream_state`

- `src/services/stream/kafka_event_consumer.py`
  - optional Kafka lifecycle event ingestion

### Presentation layer

- `src/services/presentation/stream_contract_service.py`
  - converts backend stream state into frontend-facing playback contracts

- `src/services/presentation/websocket_manager.py`
  - manages websocket client registrations and event fanout

### Realtime video layer

- `src/services/realtime_video/mediamtx_service.py`
  - writes generated MediaMTX config
  - manages a local MediaMTX process when enabled
  - verifies external MediaMTX readiness
  - reconciles runtime paths through the Control API

- `src/services/realtime_video/mediamtx_control_api.py`
  - HTTP client for MediaMTX Control API path operations

- `src/services/realtime_video/stream_manager.py`
  - worker registry
  - per-camera worker lifecycle
  - worker snapshot aggregation

- `src/services/realtime_video/frame_worker.py`
  - PyAV decode loop
  - monotonic sampling
  - reconnect logic
  - queue publication
  - metrics updates

- `src/services/realtime_video/queue.py`
  - bounded async queue with backpressure-aware behavior

### Observability

- `src/observability/metrics.py`
  - Prometheus counters, gauges, and histograms

- `src/observability/metrics_server.py`
  - standalone `/metrics` HTTP server

- `src/observability/system_metrics.py`
  - background psutil collector for CPU, memory, and network metrics

## Project Layout

```text
backend/
├── docker-compose.yaml
├── observability/
│   ├── grafana/
│   └── prometheus/
├── runtime/
│   └── mediamtx.generated.yml
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
│   │   ├── presentation/
│   │   ├── realtime_video/
│   │   └── stream/
│   └── utils/
└── tests/
```

## Camera Model

Each camera can be defined in one of two ways:

1. Direct RTSP URL
2. Components: `host + port + path + credentials`

Important camera fields:

- `id`
- `name`
- `location`
- `direct_rtsp_url`
- `host`, `port`, `path`
- `transport`
- `status`
- `metadata`
- `tags`
- `last_validation_status`
- `stream_status`

`metadata["mediamtx_stream_name"]` can override the default stream name. If that field is not present, the backend uses a normalized `camera_id`.

## Stream Lifecycle Model

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
  "timestamp": "2026-03-30T00:00:00Z",
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

`GET /streams/{camera_id}/info` and the start/stop/status APIs return a frontend-ready contract like this:

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

Notes:

- `playback_url` is the primary player URL for the requested protocol
- `access_urls.webrtc_url` is the WHEP endpoint for WebRTC playback
- `access_urls.hls_url` is the HLS fallback
- `access_urls.rtsp_pull_url` is used by backend workers, not browsers
- `worker` exposes live in-memory worker state, not just database state

## WebSocket Contract

WebSocket endpoint:

```text
ws://localhost:8000/streams/ws/updates
```

Optional filter:

```text
ws://localhost:8000/streams/ws/updates?camera_id=<camera_id>
```

Typical event types:

- `stream.snapshot`
- `stream.updated`
- `stream.connected`

The server sends an initial snapshot on connect, then pushes event-driven updates. The backend is the source of truth for stream lifecycle. The frontend should not infer lifecycle state from the media element alone.

## MediaMTX Integration

### Generated config

The backend renders:

- `runtime/mediamtx.generated.yml`

This file contains:

- API enablement
- metrics enablement
- RTSP/HLS/WebRTC listeners
- path defaults
- per-camera path definitions

### Runtime sync

For external MediaMTX mode:

- the backend writes the generated config file
- the backend authenticates to the MediaMTX Control API
- camera paths are reconciled at runtime without requiring a restart per camera change

### Control API authentication

MediaMTX Control API credentials are shared by:

- backend settings
- Docker Compose environment
- generated runtime behavior

Important variables:

- `MEDIAMTX_API_USERNAME`
- `MEDIAMTX_API_PASSWORD`

For production, keep those in deployment secrets. The code still supports a password-file fallback, but explicit env/secrets are the intended deployment path.

### External vs managed MediaMTX

The backend supports two modes:

1. Externally managed MediaMTX
   - `MEDIAMTX_MANAGE_PROCESS=false`
   - preferred for Docker and deployment environments

2. Backend-managed MediaMTX
   - `MEDIAMTX_MANAGE_PROCESS=true`
   - backend starts the `mediamtx` binary directly

The current Docker stack uses externally managed MediaMTX.

## Database Schema

### Tables

- `cameras`
- `stream_state`
- `schema_migrations`

### Migrations

- `scripts/migrations/001_create_camera_table.sql`
- `scripts/migrations/002_create_stream_table.sql`
- `scripts/migrations/003_allow_webrtc_stream_protocol.sql`

### SQL organization

Queries are stored one per file under:

- `scripts/sql/camera`
- `scripts/sql/stream`
- `scripts/sql/common`

Repositories load SQL through `src/utils/sql_loader.py`. Business logic stays in services, not in inline SQL strings.

## Observability

### Backend metrics

The backend exposes Prometheus metrics on a dedicated HTTP listener:

- `http://127.0.0.1:9109/metrics`

Metrics include:

- `frames_received_total`
- `frames_dropped_total`
- `frame_processing_latency_ms`
- `queue_size`
- `system_cpu_usage_percent`
- `process_cpu_usage_percent`
- `system_memory_usage_bytes`
- `process_memory_usage_bytes`
- `system_network_receive_bytes_total`
- `system_network_transmit_bytes_total`

### Grafana and Prometheus

Local observability assets live under:

- `observability/prometheus`
- `observability/grafana`

Docker Compose exposes:

- Prometheus on `http://localhost:9090`
- Grafana on `http://localhost:3001`

Default Grafana credentials:

- username: `admin`
- password: `admin`

## Configuration

The main runtime settings are in `src/core/config.py`.

### Required

- `database_url`

### MediaMTX

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

### Realtime workers

- `REALTIME_FRAME_SAMPLE_FPS`
- `REALTIME_FRAME_QUEUE_SIZE`
- `REALTIME_MAX_RECONNECT_ATTEMPTS`

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

## Local Development

### 1. Create the virtual environment

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
python -m venv .venv
.venv/bin/pip install -e .[dev]
```

### 2. Configure `.env`

Example:

```env
database_url=postgresql://postgres:postgres@localhost:5432/postgres
MEDIAMTX_MANAGE_PROCESS=false
MEDIAMTX_API_USERNAME=backend-control
MEDIAMTX_API_PASSWORD=replace-with-a-real-secret
MEDIAMTX_RTSP_BASE_URL=rtsp://localhost:8554
MEDIAMTX_HLS_BASE_URL=http://localhost:8888
MEDIAMTX_WEBRTC_BASE_URL=http://localhost:8889
PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

### 3. Start infrastructure

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
docker compose up -d mediamtx kafka kafka-init prometheus grafana
```

Note:

- PostgreSQL is required but is not currently provisioned in this `docker-compose.yaml`
- point `database_url` to an existing PostgreSQL instance

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

### Start a stream

```bash
curl -X POST http://127.0.0.1:8000/streams/<camera_id>/start \
  -H 'Content-Type: application/json' \
  -d '{
    "requested_protocol": "webrtc",
    "sample_fps": 1,
    "force_restart": false
  }'
```

### Fetch the player contract

```bash
curl http://127.0.0.1:8000/streams/<camera_id>/info
```

## Testing and Quality

Run the backend checks with:

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
.venv/bin/python -m ruff check src tests
.venv/bin/python -m pytest
.venv/bin/python -m pylint src tests
```

The repository is maintained with strict style expectations and a `pylint` fail-under of `10`.

## Important Notes

- Browsers never connect to RTSP directly
- WebRTC is the primary playback path
- HLS is fallback only
- WebSocket is for lifecycle state, not media
- Kafka carries metadata and events, not video frames
- The current production stream path is `MediaMTX + PyAV`, even though some older legacy modules still exist in the repository

## Legacy Modules

Some older modules remain in the tree from the earlier worker design, including:

- `src/services/stream/camera_worker.py`
- `src/services/stream/stream_manager.py`
- `src/utils/ffmpeg.py`

They are not the primary runtime path for browser playback anymore. The active architecture is:

```text
Camera -> MediaMTX -> WebRTC/HLS -> Frontend
                   -> RTSP pull -> PyAV worker -> sampled frame queue
```
