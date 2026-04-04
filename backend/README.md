# RTSP Camera Backend

FastAPI backend for a CCTV streaming platform built around MediaMTX, PostgreSQL, Kafka, PyAV frame extraction, and backend-side person tracking.

The backend is the control plane for the system:

- cameras are created, updated, validated, and deleted here
- MediaMTX paths are generated and synchronized here
- stream lifecycle state is persisted here
- WebSocket and Kafka updates originate here
- raw and tracked playback contracts are built here
- person detection, tracking, re-identification, and tracked-stream publishing run here
- Prometheus metrics for Grafana dashboards are exposed here

Browsers do not connect to RTSP cameras directly. Playback is exposed through MediaMTX, with WebRTC as the primary frontend path and HLS as the fallback.

## Core Responsibilities

- manage camera CRUD
- validate RTSP source reachability before stream start
- persist camera and stream state in PostgreSQL
- render [mediamtx.generated.yml](/home/karthik/Downloads/pipeline_opencv/backend/runtime/mediamtx.generated.yml)
- synchronize MediaMTX runtime paths through the Control API
- start and stop realtime frame workers
- start and stop tracked annotated-stream workers
- publish stream lifecycle updates over WebSocket
- consume stream lifecycle events from Kafka
- publish tracking metadata to Kafka
- expose Prometheus metrics for Grafana

## Runtime Architecture

The backend is easiest to understand as four planes:

- control plane: FastAPI, PostgreSQL, WebSocket, stream state, camera validation
- media plane: MediaMTX raw paths and tracked paths
- processing plane: PyAV frame workers and tracking workers
- observability plane: Prometheus, Grafana, exporters, runtime metrics

## High-Level Flow

```mermaid
flowchart LR
    Camera["RTSP Camera"]
    Frontend["Frontend"]
    API["FastAPI Backend"]
    DB["PostgreSQL"]
    MediaMTX["MediaMTX"]
    Kafka["Kafka"]
    WS["WebSocket"]
    PyAV["PyAV Frame Worker"]
    Detector["Roboflow Inference Detector"]
    Tracker["Roboflow ByteTrack"]
    ReID["Mobilenet Re-ID"]
    Milvus["Milvus"]
    Tracked["Tracked MediaMTX Path"]
    Prom["Prometheus"]
    Grafana["Grafana"]

    Frontend -->|REST| API
    Frontend -->|WS| WS
    WS --> API
    API --> DB
    API --> Kafka
    Kafka --> API

    Camera --> MediaMTX
    MediaMTX -->|Raw WebRTC / HLS| Frontend
    MediaMTX -->|Raw RTSP Pull| PyAV
    MediaMTX -->|Raw RTSP Pull| Detector
    Detector --> Tracker
    Tracker --> ReID
    ReID --> Milvus
    Tracker -->|Annotated RTSP Publish| Tracked
    Tracked -->|Tracked WebRTC / HLS| Frontend

    API --> Prom
    MediaMTX --> Prom
    Kafka --> Prom
    Milvus --> Prom
    Prom --> Grafana
```

## Active Stream Lifecycle

```mermaid
flowchart TD
    Start["POST /streams/{camera_id}/start"] --> Load["Load camera from PostgreSQL"]
    Load --> Validate["Validate upstream RTSP source"]
    Validate --> Sync["Render and sync MediaMTX config"]
    Sync --> Ensure["Verify MediaMTX raw + tracked paths are ready"]
    Ensure --> Persist["Persist requested stream state"]
    Persist --> Raw["Start PyAV realtime worker"]
    Raw --> TrackChoice{"Tracking enabled?"}
    TrackChoice -- Yes --> Track["Start tracking worker"]
    TrackChoice -- No --> Skip["Skip tracking worker"]
    Raw --> WSRaw["Emit stream.updated / stream.connected"]
    Track --> WSTracked["Emit tracking.updated"]
    Track --> KafkaTracked["Publish camera.tracking.updates"]
    Skip --> Contract["Return raw playback contract"]
    Track --> Contract["Return raw + tracked playback contract"]
    Contract --> FrontendRaw["Frontend can open access_urls.webrtc_url"]
    Contract --> FrontendTracked["Frontend can open tracking.access_urls.webrtc_url"]
```

## Main Components

### Application Bootstrap

Bootstrap lives in [main.py](/home/karthik/Downloads/pipeline_opencv/backend/src/main.py).

Startup sequence:

1. load settings from `.env`
2. connect to PostgreSQL
3. initialize camera, stream, MediaMTX, WebSocket, and tracking services
4. start Prometheus metrics server when enabled
5. start system and runtime metric collectors when enabled
6. sync MediaMTX config from the current camera inventory
7. start the Kafka stream consumer
8. expose the API routes and WebSocket endpoint

Shutdown sequence:

1. stop Kafka consumer
2. stop tracking Kafka producer
3. stop tracking workers
4. stop realtime frame workers
5. stop metric collectors and metrics server
6. stop managed MediaMTX if enabled
7. disconnect from PostgreSQL

### Camera Domain

Primary files:

- [camera_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/camera/camera_service.py)
- [camera_repository.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/camera/camera_repository.py)
- [camera_validator.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/camera/camera_validator.py)

Behavior:

- cameras can be created with `direct_rtsp_url` or with `host + path`
- updates regenerate MediaMTX config
- delete regenerates MediaMTX config
- validation persists the last validation result
- stream start fails fast with `503` if the upstream RTSP source is unreachable

### Stream Domain

Primary files:

- [stream_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/stream/stream_service.py)
- [stream_repository.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/stream/stream_repository.py)
- [stream_contract_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/presentation/stream_contract_service.py)

Current stream status values:

- `stopped`
- `starting`
- `running`
- `stopping`
- `reconnecting`
- `error`
- `crashed`

The backend stream state is the source of truth for the frontend. The player should not infer stream state only from browser media events.

### MediaMTX Integration

Primary files:

- [mediamtx_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/mediamtx_service.py)
- [mediamtx_control_api.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/mediamtx_control_api.py)
- [mediamtx.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/mediamtx.py)

Behavior:

- generated config is written to [mediamtx.generated.yml](/home/karthik/Downloads/pipeline_opencv/backend/runtime/mediamtx.generated.yml)
- raw camera paths are configured from the database
- tracked paths are also configured so annotated streams can be republished
- when `mediamtx_manage_process=true`, the backend can manage MediaMTX directly
- when MediaMTX runs externally, the backend reconciles runtime paths through the Control API
- stream start verifies MediaMTX readiness before workers are allowed to run

### Realtime Frame Workers

Primary files:

- [frame_worker.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/frame_worker.py)
- [stream_manager.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/stream_manager.py)
- [queue.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/queue.py)

Behavior:

- pull the raw MediaMTX RTSP path
- decode frames with PyAV
- sample frames at the configured rate
- push sampled frames into a bounded queue
- record runtime metrics such as decoded frames, sampled FPS, reconnect attempts, decode latency, and queue latency
- stop automatically after the configured reconnect limit is exhausted

### Tracking Service

All tracking code now lives under [tracking](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking).

Key files:

- [contracts.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/contracts.py)
- [worker.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/worker.py)
- [manager.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/manager.py)
- [updates.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/updates.py)
- [inference_detector.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/detectors/inference_detector.py)
- [bytetrack.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/trackers/bytetrack.py)
- [embedder.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/reid/embedder.py)
- [milvus_store.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/identity/milvus_store.py)

Current tracking pipeline:

- detector: Roboflow Inference SDK
- default detector model: `rfdetr-medium`
- target class: `person`
- tracker: Roboflow `trackers` ByteTrack
- re-id embedder: mobilenet bottleneck appearance model
- identity backend: Milvus

The tracking worker republishes an annotated MediaMTX path named:

```text
<raw_stream_name>_tracked
```

Tracked video contains drawn bounding boxes and IDs. The same tracking data is also emitted as structured metadata over WebSocket and Kafka.

### Tracking Kafka

Primary files:

- [service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking_kafka/service.py)
- [publisher.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking_kafka/publisher.py)
- [tracking_events.py](/home/karthik/Downloads/pipeline_opencv/backend/src/schemas/tracking_events.py)

Behavior:

- publishes metadata only, never raw video frames
- uses `camera_id` as the Kafka key for stable per-camera ordering
- returns a null publisher if Kafka is unavailable so tracking can continue locally

Default topic:

- `camera.tracking.updates`

### WebSocket Delivery

Primary file:

- [websocket_manager.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/presentation/websocket_manager.py)

Endpoint:

```text
/streams/ws/updates
```

Optional query parameter:

```text
?camera_id=<camera_id>
```

Frontend-facing event types include:

- `stream.snapshot`
- `stream.updated`
- `stream.connected`
- `stream.disconnected`
- `tracking.updated`

## API Surface

### Camera Routes

Defined in [camera_routes.py](/home/karthik/Downloads/pipeline_opencv/backend/src/routes/camera_routes.py).

- `POST /cameras`
- `GET /cameras`
- `GET /cameras/{camera_id}`
- `PUT /cameras/{camera_id}`
- `DELETE /cameras/{camera_id}`
- `POST /cameras/{camera_id}/validate`

### Stream Routes

Defined in [stream_routes.py](/home/karthik/Downloads/pipeline_opencv/backend/src/routes/stream_routes.py).

- `POST /streams/{camera_id}/start`
- `POST /streams/{camera_id}/stop`
- `GET /streams/{camera_id}/status`
- `GET /streams/{camera_id}/info`
- `WS /streams/ws/updates`

`POST /streams/{camera_id}/start` accepts:

- `force_restart`
- `requested_protocol`
- `sample_fps`
- `enable_tracking_events`
- `reason`

### Health Routes

Defined in [health_routes.py](/home/karthik/Downloads/pipeline_opencv/backend/src/routes/health_routes.py).

- `GET /health`
- `GET /health/db`
- `GET /health/stream/{camera_id}`

## Stream Contract

The frontend contract is built in [stream_contract_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/presentation/stream_contract_service.py) and serialized by [stream_responses.py](/home/karthik/Downloads/pipeline_opencv/backend/src/schemas/stream_responses.py).

Top-level fields include:

- `camera_id`
- `camera_name`
- `stream_id`
- `stream_name`
- `status`
- `protocol`
- `playback_url`
- `access_urls.webrtc_url`
- `access_urls.hls_url`
- `access_urls.rtsp_pull_url`
- `websocket_url`
- `fallback`
- `last_error_code`
- `last_error_message`
- `worker`
- `tracking`

The important split is:

- raw stream: `playback_url` and `access_urls.*`
- tracked stream: `tracking.access_urls.*`

If the frontend opens the tracked URLs, it will see the annotated video stream with boxes and IDs. If it opens the raw URLs, it will see the unannotated camera feed.

### Tracking Section

When tracking is enabled, `tracking` contains:

- `enabled`
- `stream_name`
- `access_urls.webrtc_url`
- `access_urls.hls_url`
- `access_urls.rtsp_pull_url`
- `is_registered`
- `is_process_alive`
- `reconnect_attempts`
- `active_tracks`
- `identity_backend`
- `last_error_message`
- `tracks[]`

Each `tracks[]` item contains:

- `track_id`
- `persistent_id`
- `class_name`
- `confidence`
- `similarity`
- `left`
- `top`
- `width`
- `height`

## Data Model

SQL migrations live in [scripts/migrations](/home/karthik/Downloads/pipeline_opencv/backend/scripts/migrations).

Current migrations:

- [001_create_camera_table.sql](/home/karthik/Downloads/pipeline_opencv/backend/scripts/migrations/001_create_camera_table.sql)
- [002_create_stream_table.sql](/home/karthik/Downloads/pipeline_opencv/backend/scripts/migrations/002_create_stream_table.sql)
- [003_allow_webrtc_stream_protocol.sql](/home/karthik/Downloads/pipeline_opencv/backend/scripts/migrations/003_allow_webrtc_stream_protocol.sql)

Main entities:

- camera records
- stream records

The database is not started by [docker-compose.yaml](/home/karthik/Downloads/pipeline_opencv/backend/docker-compose.yaml). You need a running PostgreSQL instance and a valid `DATABASE_URL`.

## Configuration

Runtime settings live in [config.py](/home/karthik/Downloads/pipeline_opencv/backend/src/core/config.py) and are loaded from `.env`.

Important variables:

- `DATABASE_URL`
- `KAFKA_BOOTSTRAP_SERVERS`
- `MEDIAMTX_API_BASE_URL`
- `MEDIAMTX_API_USERNAME`
- `MEDIAMTX_API_PASSWORD`
- `MEDIAMTX_RTSP_BASE_URL`
- `MEDIAMTX_HLS_BASE_URL`
- `MEDIAMTX_WEBRTC_BASE_URL`
- `TRACKING_DETECTOR_MODEL_ID`
- `TRACKING_DETECTOR_API_KEY`
- `TRACKING_IDENTITY_STORE_URI`
- `TRACKING_IDENTITY_STORE_TOKEN`
- `TRACKING_SAMPLE_FPS`
- `TRACKING_OUTPUT_FPS`
- `METRICS_ENABLED`
- `METRICS_PORT`

Recommended host-run development values:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/rtsp_camera
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
MEDIAMTX_API_BASE_URL=http://localhost:9997
MEDIAMTX_API_USERNAME=backend-control
MEDIAMTX_API_PASSWORD=backend-control-dev-secret
MEDIAMTX_RTSP_BASE_URL=rtsp://localhost:8554
MEDIAMTX_HLS_BASE_URL=http://localhost:8888
MEDIAMTX_WEBRTC_BASE_URL=http://localhost:8889
TRACKING_DETECTOR_MODEL_ID=rfdetr-medium
TRACKING_IDENTITY_STORE_URI=http://localhost:19530
METRICS_ENABLED=true
METRICS_PORT=9109
```

Milvus options:

- if the backend runs on the host and you want Docker Milvus, use `http://localhost:19530`
- if the backend runs in Docker and you want Docker Milvus, use `http://milvus:19530`
- if you want Milvus Lite instead, leave the default local file path in place:
  - [milvus_tracking.db](/home/karthik/Downloads/pipeline_opencv/backend/runtime/milvus_tracking.db)

## Local Infrastructure

[docker-compose.yaml](/home/karthik/Downloads/pipeline_opencv/backend/docker-compose.yaml) starts the backend support stack:

- `mediamtx`
- `etcd`
- `minio`
- `milvus`
- `kafka`
- `kafka-init`
- `node-exporter`
- `postgres-exporter`
- `prometheus`
- `grafana`

If you run the backend on the host and want to use the Docker Milvus service instead of the local Lite file, set:

```env
TRACKING_IDENTITY_STORE_URI=http://localhost:19530
```

What Compose does not start:

- PostgreSQL
- the FastAPI application itself

Bring up the support stack:

```bash
cd backend
docker compose up -d
```

Run the backend:

```bash
cd backend
uvicorn src.main:app --reload
```

## Observability

Application metrics and collectors live under [src/observability](/home/karthik/Downloads/pipeline_opencv/backend/src/observability).

Key files:

- [metrics.py](/home/karthik/Downloads/pipeline_opencv/backend/src/observability/metrics.py)
- [metrics_server.py](/home/karthik/Downloads/pipeline_opencv/backend/src/observability/metrics_server.py)
- [http_middleware.py](/home/karthik/Downloads/pipeline_opencv/backend/src/observability/http_middleware.py)
- [system_metrics.py](/home/karthik/Downloads/pipeline_opencv/backend/src/observability/system_metrics.py)
- [runtime_metrics.py](/home/karthik/Downloads/pipeline_opencv/backend/src/observability/runtime_metrics.py)

Current observability stack:

- backend Prometheus endpoint on `:9109`
- MediaMTX metrics on `:9998`
- Kafka JMX exporter on `:7071`
- Node Exporter on `:9100`
- Postgres Exporter on `:9187`
- Milvus health and metrics on `:9091`
- Prometheus on `:9090`
- Grafana on `:3001`

Prometheus configuration:

- [prometheus.yml.tmpl](/home/karthik/Downloads/pipeline_opencv/backend/observability/prometheus/prometheus.yml.tmpl)
- [alerts.yml](/home/karthik/Downloads/pipeline_opencv/backend/observability/prometheus/alerts.yml)

Grafana dashboards:

- [realtime_video_pipeline.json](/home/karthik/Downloads/pipeline_opencv/backend/observability/grafana/dashboards/realtime_video_pipeline.json)
- [platform_infrastructure.json](/home/karthik/Downloads/pipeline_opencv/backend/observability/grafana/dashboards/platform_infrastructure.json)

## Source Layout

```text
backend/
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
│   │   ├── stream/
│   │   ├── tracking/
│   │   │   ├── detectors/
│   │   │   ├── identity/
│   │   │   ├── reid/
│   │   │   └── trackers/
│   │   └── tracking_kafka/
│   └── utils/
├── scripts/
│   └── migrations/
├── observability/
│   ├── grafana/
│   ├── kafka_jmx/
│   ├── postgres_exporter/
│   └── prometheus/
├── runtime/
└── README.md
```

## Development

Install dependencies:

```bash
cd backend
uv sync
```

Run the API:

```bash
cd backend
uvicorn src.main:app --reload
```

Quality checks:

```bash
cd backend
.venv/bin/python -m ruff check src tests
PYLINTHOME=/tmp/pylint .venv/bin/python -m pylint src tests
.venv/bin/python -m pytest
```

## Troubleshooting

### FastAPI stops during startup

Check these first:

- `DATABASE_URL` points to a reachable PostgreSQL instance
- `MEDIAMTX_API_BASE_URL` points to MediaMTX Control API
- `TRACKING_IDENTITY_STORE_URI` matches how Milvus is running

Common examples:

- host-run backend with Docker Milvus:
  - `TRACKING_IDENTITY_STORE_URI=http://localhost:19530`
- Dockerized backend with Docker Milvus:
  - `TRACKING_IDENTITY_STORE_URI=http://milvus:19530`

### Stream start returns `503`

Most common causes:

- upstream RTSP source is unreachable
- MediaMTX path is not ready
- the camera source itself is offline

### Tracked stream exists but the frontend shows raw video

Make sure the frontend is opening:

- `tracking.access_urls.webrtc_url`

instead of:

- `playback_url`
- `access_urls.webrtc_url`

### Prometheus or Grafana ports are not shown in `docker compose ps`

`prometheus`, `grafana`, `node-exporter`, and `postgres-exporter` use host networking. Open them directly on the host:

- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3001`

## Notes

- The backend currently uses Roboflow Inference plus Roboflow Trackers for tracking-by-detection.
- The tracked stream is a second MediaMTX path, not a frontend overlay layer.
- Kafka carries metadata and lifecycle events, not raw video.
- Persistent cross-camera identity depends on Milvus availability. If Milvus is unavailable, tracking can continue with local track IDs but without stable persistent identity assignment.
