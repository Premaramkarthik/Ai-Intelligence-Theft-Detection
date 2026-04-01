# RTSP Camera Backend

FastAPI backend for a real-time CCTV platform built around MediaMTX, PostgreSQL, Kafka, PyAV frame sampling, and backend-side person tracking.

The backend is the control plane for the system:

- cameras are registered and validated here
- MediaMTX paths are generated and synchronized here
- stream lifecycle is persisted here
- WebSocket and Kafka updates originate here
- tracking and re-identification run here

Browsers do not connect to RTSP directly. Playback is exposed through MediaMTX as WebRTC first and HLS second.

## What The Backend Does

- manages camera CRUD
- validates RTSP reachability
- stores camera and stream state in PostgreSQL
- renders `runtime/mediamtx.generated.yml`
- synchronizes MediaMTX runtime paths through the Control API
- starts PyAV-based realtime frame workers
- starts tracked annotated-stream workers
- republishes tracked video back into MediaMTX
- publishes lifecycle updates over WebSocket
- consumes stream lifecycle events from Kafka
- publishes tracking updates to Kafka
- exposes Prometheus metrics for Grafana dashboards

## Runtime Architecture

The backend is split into four practical planes:

- control plane: FastAPI + PostgreSQL + WebSocket
- media plane: MediaMTX
- processing plane: PyAV workers + tracking workers
- observability plane: Prometheus + Grafana

### High-Level Flow

```mermaid
flowchart LR
    Camera["RTSP Camera"]
    MediaMTX["MediaMTX"]
    Frontend["Frontend Player"]
    API["FastAPI Backend"]
    DB["PostgreSQL"]
    WS["WebSocket"]
    Kafka["Kafka"]
    PyAV["PyAV Frame Worker"]
    Tracking["Tracking Worker"]
    ByteTrack["Roboflow ByteTrack"]
    ReID["Mobilenet Re-ID"]
    Milvus["Milvus"]
    Tracked["Tracked MediaMTX Path"]
    Metrics["Prometheus / Grafana"]

    Camera --> MediaMTX
    Frontend -->|REST| API
    Frontend -->|WS| WS
    WS --> API
    API --> DB
    API --> Kafka
    Kafka --> API
    MediaMTX -->|Raw WHEP / HLS| Frontend
    MediaMTX -->|Raw RTSP Pull| PyAV
    MediaMTX -->|Raw RTSP Pull| Tracking
    PyAV --> Metrics
    Tracking --> ByteTrack
    ByteTrack --> ReID
    ReID --> Milvus
    Tracking -->|Annotated RTSP Publish| Tracked
    Tracked -->|Tracked WHEP / HLS| Frontend
    API --> Metrics
    Tracking --> Metrics
```

### Active Stream Lifecycle

```mermaid
flowchart TD
    Start["POST /streams/{camera_id}/start"] --> LoadCamera["Load camera from PostgreSQL"]
    LoadCamera --> SyncConfig["Render and sync MediaMTX config"]
    SyncConfig --> EnsurePath["Verify MediaMTX path is ready"]
    EnsurePath --> PersistStart["Persist stream requested state"]
    PersistStart --> StartWorker["Start PyAV realtime worker"]
    StartWorker --> TrackingDecision{"Tracking enabled?"}
    TrackingDecision -- Yes --> StartTracking["Start tracking worker"]
    TrackingDecision -- No --> SkipTracking["Skip tracking worker"]
    StartTracking --> RawContract["Return raw playback contract"]
    SkipTracking --> RawContract
    RawContract --> RawPlayback["Frontend opens raw playback_url or access_urls.webrtc_url"]
    StartTracking --> TrackedPlayback["Frontend can also open tracking.access_urls.webrtc_url"]
    StartWorker --> WSUpdates["WebSocket emits stream.updated / stream.connected"]
    StartTracking --> TrackingUpdates["WebSocket and Kafka emit tracking.updated"]
```

## Main Components

### FastAPI App

Application bootstrap lives in [main.py](/home/karthik/Downloads/pipeline_opencv/backend/src/main.py).

On startup it:

- loads settings from `.env`
- connects to PostgreSQL
- initializes camera and stream services
- writes and syncs MediaMTX config
- starts Prometheus metrics when enabled
- starts the stream Kafka consumer
- starts tracking runtime services

### MediaMTX Integration

MediaMTX orchestration lives in:

- [mediamtx_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/mediamtx_service.py)
- [mediamtx_control_api.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/mediamtx_control_api.py)
- [mediamtx.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/mediamtx.py)

Current behavior:

- generated config is written to [mediamtx.generated.yml](/home/karthik/Downloads/pipeline_opencv/backend/runtime/mediamtx.generated.yml)
- when `mediamtx_manage_process=true`, the backend can run MediaMTX itself
- when using an external MediaMTX service, the backend reconciles paths through the Control API at `MEDIAMTX_API_BASE_URL`
- stream start verifies that the requested path is present before workers run

### Camera Domain

Camera logic lives in:

- [camera_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/camera/camera_service.py)
- [camera_repository.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/camera/camera_repository.py)
- [camera_validator.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/camera/camera_validator.py)

A camera can be created in one of two ways:

1. `direct_rtsp_url`
2. `host + port + path` with optional credentials

Supported camera status values:

- `active`
- `inactive`
- `error`

### Stream Domain

Stream orchestration lives in:

- [stream_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/stream/stream_service.py)
- [stream_repository.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/stream/stream_repository.py)
- [stream_contract_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/presentation/stream_contract_service.py)

Current stream lifecycle values:

- `stopped`
- `starting`
- `running`
- `stopping`
- `reconnecting`
- `error`
- `crashed`

The backend lifecycle state is the source of truth for the frontend. The player should not infer lifecycle state from WebRTC behavior alone.

### Realtime Frame Worker

PyAV worker logic lives in:

- [frame_worker.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/frame_worker.py)
- [stream_manager.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/stream_manager.py)
- [queue.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/realtime_video/queue.py)

What it does:

- pulls the raw MediaMTX RTSP path
- decodes frames with PyAV
- samples frames at the configured FPS
- pushes sampled frames into the shared queue
- records runtime metrics like FPS, decode time, queue latency, reconnect attempts

### Tracking Service

Tracking code now lives entirely under [tracking](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking).

Key modules:

- [worker.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/worker.py)
- [manager.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/manager.py)
- [updates.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/updates.py)
- [yolo26_detector.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/detectors/yolo26_detector.py)
- [bytetrack.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/trackers/bytetrack.py)
- [embedder.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/reid/embedder.py)
- [milvus_store.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking/identity/milvus_store.py)

Tracking behavior:

- detector: YOLO26 ONNX through OpenCV DNN
- tracker: Roboflow Trackers ByteTrack
- re-id embedder: mobilenet bottleneck appearance model
- persistent identity backend: Milvus

The tracking worker republishes a second annotated MediaMTX path named:

```text
<raw_stream_name>_tracked
```

### Tracking Kafka

Tracking Kafka integration lives in:

- [service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking_kafka/service.py)
- [publisher.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/tracking_kafka/publisher.py)
- [tracking_events.py](/home/karthik/Downloads/pipeline_opencv/backend/src/schemas/tracking_events.py)

It publishes metadata only, not video frames.

Default topic:

- `camera.tracking.updates`

### WebSocket

WebSocket fanout is handled by:

- [websocket_manager.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/presentation/websocket_manager.py)

The stream WebSocket endpoint is:

```text
/streams/ws/updates
```

Optional query parameter:

```text
?camera_id=<camera_id>
```

Current event types used by the frontend include:

- `stream.snapshot`
- `stream.updated`
- `stream.connected`
- `tracking.updated`

## API Surface

### Camera Endpoints

Defined in [camera_routes.py](/home/karthik/Downloads/pipeline_opencv/backend/src/routes/camera_routes.py).

- `POST /cameras`
- `GET /cameras`
- `GET /cameras/{camera_id}`
- `PUT /cameras/{camera_id}`
- `DELETE /cameras/{camera_id}`
- `POST /cameras/{camera_id}/validate`

### Stream Endpoints

Defined in [stream_routes.py](/home/karthik/Downloads/pipeline_opencv/backend/src/routes/stream_routes.py).

- `POST /streams/{camera_id}/start`
- `POST /streams/{camera_id}/stop`
- `GET /streams/{camera_id}/status`
- `GET /streams/{camera_id}/info`
- `WS /streams/ws/updates`

### Health Endpoints

Defined in [health_routes.py](/home/karthik/Downloads/pipeline_opencv/backend/src/routes/health_routes.py).

- `GET /health`
- `GET /health/db`
- `GET /health/stream/{camera_id}`

## Stream Contract

The frontend-ready contract is built by [stream_contract_service.py](/home/karthik/Downloads/pipeline_opencv/backend/src/services/presentation/stream_contract_service.py) and returned by:

- `GET /streams/{camera_id}/info`
- `GET /streams/{camera_id}/status`
- `POST /streams/{camera_id}/start`
- `POST /streams/{camera_id}/stop`

Important fields in `data`:

- `status`
- `protocol`
- `playback_url`
- `access_urls.webrtc_url`
- `access_urls.hls_url`
- `access_urls.rtsp_pull_url`
- `websocket_url`
- `tracking`
- `worker`

### Raw vs Tracked Playback

Raw stream:

- `playback_url`
- `access_urls.webrtc_url`
- `access_urls.hls_url`

Tracked annotated stream:

- `tracking.access_urls.webrtc_url`
- `tracking.access_urls.hls_url`
- `tracking.access_urls.rtsp_pull_url`

Important: the default `playback_url` still points to the raw stream. If the frontend wants boxes and IDs burned into the video, it must explicitly open the tracked stream URL from `tracking.access_urls`.

### Worker Section

The `worker` object reflects realtime backend worker state, including:

- `desired_state`
- `is_registered`
- `is_process_alive`
- `restart_count`
- `reconnect_attempts`
- `sampled_frames`
- `dropped_frames`
- `current_fps`
- `queue_latency_ms`
- `decode_time_ms`

### Tracking Section

When tracking is enabled, `tracking` includes:

- `enabled`
- `stream_name`
- `access_urls`
- `is_registered`
- `is_process_alive`
- `reconnect_attempts`
- `active_tracks`
- `identity_backend`
- `last_error_message`
- `tracks[]`

Each `tracks[]` item currently includes:

- `track_id`
- `persistent_id`
- `class_name`
- `confidence`
- `similarity`
- `left`
- `top`
- `width`
- `height`

## Local Development

### Infrastructure Services

[docker-compose.yaml](/home/karthik/Downloads/pipeline_opencv/backend/docker-compose.yaml) starts:

- MediaMTX
- Kafka
- Kafka topic init job
- etcd
- MinIO
- Milvus standalone
- Prometheus
- Grafana

It does not start PostgreSQL. You need a running Postgres instance and a valid `DATABASE_URL`.

Start infra:

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
docker compose up -d mediamtx etcd minio milvus kafka kafka-init prometheus grafana
```

Important local ports:

- backend API: `8000`
- MediaMTX RTSP: `8554`
- MediaMTX HLS: `8888`
- MediaMTX WebRTC/WHEP: `8889`
- MediaMTX WebRTC UDP: `8189/udp`
- MediaMTX Control API: `9997`
- MediaMTX metrics/pprof: `9998`
- Kafka: `9092`
- Milvus: `19530`
- Milvus health: `9091`
- Prometheus: `9090`
- Grafana: `3001`
- backend metrics: `9109`

### Running The API

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
uvicorn src.main:app --reload
```

### Typical Local `.env` Values

At minimum:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/rtsp_camera
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
MEDIAMTX_API_BASE_URL=http://localhost:9997
MEDIAMTX_RTSP_BASE_URL=rtsp://localhost:8554
MEDIAMTX_HLS_BASE_URL=http://localhost:8888
MEDIAMTX_WEBRTC_BASE_URL=http://localhost:8889
TRACKING_IDENTITY_STORE_URI=http://localhost:19530
MEDIAMTX_API_USERNAME=backend-control
MEDIAMTX_API_PASSWORD=backend-control-dev-secret
```

If you want Milvus Lite instead of Docker Milvus for development, leave `TRACKING_IDENTITY_STORE_URI` unset and the backend will use:

```text
runtime/milvus_tracking.db
```

## Operational Notes

### MediaMTX Auth

The backend expects MediaMTX Control API credentials to match:

- `MEDIAMTX_API_USERNAME`
- `MEDIAMTX_API_PASSWORD`

Those credentials must be aligned between the backend and the MediaMTX container startup config.

### Tracking Startup

Tracking runtime services are created in [tracking_bootstrap.py](/home/karthik/Downloads/pipeline_opencv/backend/src/utils/tracking_bootstrap.py).

Startup path:

- start tracking Kafka producer
- initialize Milvus identity store
- create YOLO26 detector
- create tracking manager
- wire WebSocket + Kafka fanout publishers

### Kafka Behavior

The stream Kafka consumer is part of the main app and is started in [main.py](/home/karthik/Downloads/pipeline_opencv/backend/src/main.py).

Tracking Kafka publishing is more defensive:

- if Kafka is disabled, a null publisher is used
- if the tracking producer cannot start, tracking still runs and WebSocket updates continue

## Observability

Prometheus metrics are exposed by the backend metrics server and scraped by the included Prometheus configuration.

Observability files live under:

- [observability/prometheus](/home/karthik/Downloads/pipeline_opencv/backend/observability/prometheus)
- [observability/grafana](/home/karthik/Downloads/pipeline_opencv/backend/observability/grafana)
- [observability/grafana/dashboards](/home/karthik/Downloads/pipeline_opencv/backend/observability/grafana/dashboards)

## Project Layout

```text
backend/
├── docker-compose.yaml
├── model_repository/
│   ├── cnn_transformers/
│   ├── hf_vjepa2_finetune/
│   └── yolo/
├── observability/
├── runtime/
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
│   │   ├── stream/
│   │   ├── tracking/
│   │   │   ├── detectors/
│   │   │   ├── identity/
│   │   │   ├── reid/
│   │   │   └── trackers/
│   │   └── tracking_kafka/
│   └── utils/
└── tests/
```

## Quality Commands

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
.venv/bin/ruff check .
PYTHONPATH=. MPLCONFIGDIR=/tmp/matplotlib .venv/bin/pylint src tests
.venv/bin/pytest
```

## Current Tracking Stack Summary

The backend no longer uses the old Deep SORT tracking algorithm.

Current production tracking stack:

- person detector: YOLO26 ONNX
- tracker: Roboflow Trackers ByteTrack
- re-id embedder: mobilenet bottleneck appearance model
- persistent identity store: Milvus
- tracked stream output: MediaMTX `<stream_name>_tracked`
