# RTSP Camera Backend

Production-oriented FastAPI backend for camera management, MediaMTX-based stream distribution, PyAV frame extraction, PostgreSQL persistence, and frontend-friendly stream contracts.

## Overview

This backend separates the control plane from the media plane:

- FastAPI manages cameras, stream lifecycle, health, and frontend contracts.
- MediaMTX handles RTSP ingest, WebRTC fanout, and HLS fallback delivery.
- PyAV workers pull streams from MediaMTX for sampled frame extraction.
- PostgreSQL stores camera and stream state.
- Kafka is optional and is used only for metadata and event propagation, never for video frames.

The current stream APIs return MediaMTX playback endpoints directly, so frontend clients can open WebRTC first and fall back to HLS without custom translation logic.

## Architecture

### System Diagram

```mermaid
flowchart LR
    Camera["RTSP Cameras"]
    MediaMTX["MediaMTX\nRTSP ingest + WebRTC + HLS"]
    Frontend["Frontend\nPlayer + Dashboard"]
    FastAPI["FastAPI\nControl Plane"]
    PyAV["PyAV Realtime Workers\nSampled frame extraction"]
    Queue["Async Frame Queue"]
    Kafka["Kafka\nOptional metadata/events"]
    Postgres["PostgreSQL"]
    WS["WebSocket Clients"]

    Camera --> MediaMTX
    MediaMTX --> Frontend
    MediaMTX --> PyAV
    PyAV --> Queue
    PyAV -. metadata only .-> Kafka
    Frontend -->|REST| FastAPI
    FastAPI --> Postgres
    FastAPI -->|stream contracts| Frontend
    FastAPI -->|optional consumer| Kafka
    FastAPI -->|WebSocket updates| WS
```

### Request and Playback Flow

```mermaid
sequenceDiagram
    participant UI as Frontend
    participant API as FastAPI
    participant DB as PostgreSQL
    participant MM as MediaMTX
    participant Worker as PyAV Worker

    UI->>API: POST /streams/{camera_id}/start
    API->>DB: upsert stream_state
    API->>Worker: start sampled frame worker
    Worker->>MM: pull rtsp://mediamtx:8554/{stream_name}
    API-->>UI: stream info contract\nwebrtc_url + hls_url + websocket_url
    UI->>MM: open WebRTC WHEP URL
    UI->>API: connect /streams/ws/updates
```

## Runtime Components

- [main.py](/home/karthik/Downloads/pipeline_opencv/backend/src/main.py)
  Initializes FastAPI, PostgreSQL, the MediaMTX-backed stream manager, the stream contract service, Kafka consumer, routes, and CORS.

- [stream_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/stream/stream_service.py)
  Implements the stream control plane used by `start`, `stop`, `status`, `info`, and stream health.

- [stream_contract_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/presentation/stream_contract_service.py)
  Builds frontend-ready responses with WebRTC, HLS, and RTSP pull URLs.

- [realtime_video/stream_manager.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/stream_manager.py)
  Runs many PyAV frame workers inside one asyncio process and exposes worker snapshots to the API layer.

- [realtime_video/frame_worker.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/frame_worker.py)
  Connects to MediaMTX RTSP paths with PyAV, samples frames at a configurable FPS, and reconnects with backoff.

- [realtime_video/queue.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/queue.py)
  Provides the bounded in-memory async queue used by sampled frame workers.

- [realtime_video/mediamtx.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/mediamtx.py)
  Normalizes MediaMTX stream names and builds WebRTC, HLS, and RTSP pull endpoints.

- [mediamtx.yml](/home/karthik/Downloads/pipeline_opencv/backend/mediamtx.yml)
  Defines the MediaMTX server with RTSP over TCP, WebRTC, low-latency HLS, API, metrics, and on-demand behavior.

## API Contract

All HTTP endpoints use the same success and error envelope shape.

Success:

```json
{
  "status": "success",
  "message": "Stream info fetched successfully.",
  "data": {}
}
```

Error:

```json
{
  "status": "error",
  "message": "Camera not found",
  "error_code": "CAMERA_NOT_FOUND",
  "data": null
}
```

The shared response helpers live in [response.py](/home/karthik/Downloads/pipeline_opencv/backend/src/utils/response.py), and exception mapping lives in [handler.py](/home/karthik/Downloads/pipeline_opencv/backend/src/core/exceptions/handler.py).

## Stream APIs

- `POST /streams/{camera_id}/start`
- `POST /streams/{camera_id}/stop`
- `GET /streams/{camera_id}/status`
- `GET /streams/{camera_id}/info`
- `WS /streams/ws/updates`

The stream response now includes MediaMTX-native access URLs:

```json
{
  "camera_id": "cam_001",
  "camera_name": "Front Gate",
  "stream_id": "stream_cam_001",
  "stream_name": "cam_001",
  "status": "running",
  "protocol": "webrtc",
  "playback_url": "http://localhost:8889/cam_001/whep",
  "access_urls": {
    "webrtc_url": "http://localhost:8889/cam_001/whep",
    "hls_url": "http://localhost:8888/cam_001/index.m3u8",
    "rtsp_pull_url": "rtsp://localhost:8554/cam_001"
  },
  "websocket_url": "ws://localhost:8000/streams/ws/updates"
}
```

### Stream Name Resolution

Each camera maps to a MediaMTX path name:

- If `camera.metadata["mediamtx_stream_name"]` is present, that value is used.
- Otherwise the backend uses a normalized form of `camera_id`.

That lets the API remain stable while MediaMTX paths stay explicit and predictable.

## Camera APIs

- `POST /cameras`
- `GET /cameras`
- `GET /cameras/{camera_id}`
- `PUT /cameras/{camera_id}`
- `DELETE /cameras/{camera_id}`
- `POST /cameras/{camera_id}/validate`

Interactive docs are available at:

- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

## Database and SQL Layout

Migrations create these tables:

- `cameras`
- `stream_state`
- `schema_migrations`

Migration files:

- [001_create_camera_table.sql](/home/karthik/Downloads/pipeline_opencv/backend/scripts/migrations/001_create_camera_table.sql)
- [002_create_stream_table.sql](/home/karthik/Downloads/pipeline_opencv/backend/scripts/migrations/002_create_stream_table.sql)

Migration runner:

- [migration_runner.py](/home/karthik/Downloads/pipeline_opencv/backend/src/utils/migration_runner.py)

SQL is stored one query per file:

```text
scripts/sql/
  camera/
    insert_camera.sql
    get_camera_by_id.sql
    list_cameras.sql
    update_camera.sql
    delete_camera.sql
    update_camera_validation.sql
  stream/
    insert_stream.sql
    get_stream.sql
    list_streams.sql
    update_stream_status.sql
    apply_stream_event.sql
  common/
    health_check.sql
```

Repositories load these files through [sql_loader.py](/home/karthik/Downloads/pipeline_opencv/backend/src/utils/sql_loader.py). Services do not contain inline SQL.

## MediaMTX and Realtime Video Settings

Key runtime settings live in [config.py](/home/karthik/Downloads/pipeline_opencv/backend/src/core/config.py):

- `MEDIAMTX_RTSP_BASE_URL`
- `MEDIAMTX_HLS_BASE_URL`
- `MEDIAMTX_WEBRTC_BASE_URL`
- `REALTIME_FRAME_SAMPLE_FPS`
- `REALTIME_FRAME_QUEUE_SIZE`
- `PUBLIC_API_BASE_URL`
- `PUBLIC_WS_BASE_URL`

The backend assumes MediaMTX path definitions already exist in [mediamtx.yml](/home/karthik/Downloads/pipeline_opencv/backend/mediamtx.yml) or are managed externally.

## Kafka Usage

Kafka is optional and used only for metadata and lifecycle events.

Topics:

- `camera.status`
- `camera.events`
- `camera.ai_results`

Kafka is not used for decoded frames or raw video transport.

## WebSocket Contract

Frontend clients can connect to:

```text
ws://localhost:8000/streams/ws/updates
```

Optional query parameter:

```text
?camera_id=<camera_id>
```

On connect, the API sends an initial snapshot and later pushes stream update envelopes.

## Local Development

### 1. Install dependencies

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
python -m venv .venv
.venv/bin/pip install -e .[dev]
```

### 2. Configure environment

Create or update [`.env`](/home/karthik/Downloads/pipeline_opencv/backend/.env):

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
PUBLIC_API_BASE_URL=http://localhost:8000
MEDIAMTX_RTSP_BASE_URL=rtsp://localhost:8554
MEDIAMTX_HLS_BASE_URL=http://localhost:8888
MEDIAMTX_WEBRTC_BASE_URL=http://localhost:8889
KAFKA_ENABLED=false
```

### 3. Start MediaMTX

Run MediaMTX with the provided config:

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
mediamtx mediamtx.yml
```

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

### 6. Optional Kafka

If you want Kafka locally:

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
docker compose up -d kafka
docker compose up --force-recreate kafka-init
```

## Verification

Quality checks used for this backend:

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
.venv/bin/python -m ruff check src tests
.venv/bin/python -m pytest tests
.venv/bin/python -m pylint src tests
```

## Notes

- MediaMTX is the media plane. FastAPI is the control plane.
- WebRTC is the primary frontend playback path.
- HLS is the fallback path.
- PyAV workers pull from MediaMTX, not from cameras directly.
- The backend is AI-ready for future frame consumers, but it does not include any model or inference code.
