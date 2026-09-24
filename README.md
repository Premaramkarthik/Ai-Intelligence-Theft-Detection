# Ai Intelligence Theft Detection
# Real-Time AI Video Intelligence & Person Tracking Platform

A multi-camera video intelligence platform that ingests live RTSP feeds, detects and tracks people in real time, resolves persistent identities across reconnects and cameras, and streams the annotated video plus structured events out over WebSocket and Kafka.

The system is built as two cooperating pieces:

- **Backend** (`backend/`) — a Python/FastAPI control plane plus an OpenCV-based edge processing pipeline for detection, tracking, re-identification, and inference.
- **Frontend** (`frontend/`) — a Next.js dashboard for managing cameras and viewing live tracked streams.

## What it does

1. Register an RTSP camera through the API. The backend validates connectivity and generates a [MediaMTX](https://github.com/bluenviron/mediamtx) playback path for it.
2. Starting a stream spins up an edge pipeline worker that pulls the raw feed and runs it through detection, tracking, and identity resolution.
3. A re-identified, annotated stream is republished to a second MediaMTX path so the frontend (or any RTSP/WebRTC/HLS client) can watch tracked video directly.
4. Tracking and identity events are broadcast live over WebSocket and published to Kafka for downstream consumers.
5. Metrics for every stage (queue depth, detector throughput, embedding latency, Kafka health) are exposed to Prometheus/Grafana.

## Architecture

### Edge processing pipeline

The core of the system is a 12-stage OpenCV-based pipeline (`backend/src/opencv_pipeline/`), designed against verified OpenCV/Ultralytics/ByteTrack/Torchreid references (see [`backend/docs/opencv_pipeline_architecture.md`](backend/docs/opencv_pipeline_architecture.md) for the full design and citations):

```
Camera / RTSP
     |
VideoCaptureWorker  --per-camera capture, reconnect w/ backoff
     |
FrameBuffer  --backpressure            MultiCameraSynchronizer  --timestamp alignment
     |                                          |
     +------------------+-----------------------+
                         |
              FramePreprocessor   --resize, color convert, low-light flag
                         |
              CalibrationService  --undistort, homography, world projection
                         |
              OpticalFlowStabilizer  --Lucas-Kanade + affine stabilization
                         |
              MotionAnalyzer  --Farneback flow + background subtraction
                         |
              YOLOBatchDetector  --batched Ultralytics person detection
                         |
              ByteTrackStage  --per-camera local track identity
                         |
              BodyReIdentifier  --batched appearance embeddings
                         |
              IdentityAssignmentService  --Milvus global identity resolution
                         |
              OutputDispatcher  --annotation, Kafka fanout, WebSocket updates
                         |
        +----------------+------------------------+
        |                |                         |
tracking.updates    camera.frames            identity.events
        |                |                         |
        +----------------+------------------------+
                         |
                       Kafka
                         |
        +----------------+------------------------+
        |                                          |
InferenceManager / Triton                  StreamEventConsumer
        |                                          |
PostgreSQL (camera.ai_results)         WebSocketManager -> frontend
```

### Backend control plane

`backend/src/main.py` runs the FastAPI application: camera CRUD, RTSP validation, MediaMTX path generation and readiness, stream lifecycle management, the WebSocket manager, and the Kafka event bridge. See [`backend/README.md`](backend/README.md) for a full breakdown of every module, the active vs. legacy code paths, and known integration gaps.

### Identity resolution

Each tracked person gets a local track ID per camera and, once enough appearance evidence accumulates, a persistent global identity resolved against a shared [Milvus](https://milvus.io/) vector collection. Identity lifecycle events (`create` / `update` / `merge` / `expire`) are emitted to Kafka so downstream systems can react to a person reappearing on a different camera.

### Observability

Every stage reports queue depth, latency, and throughput to Prometheus. Bundled Grafana dashboards visualize pipeline health, and structured logs / Loki are wired in through the local infrastructure stack.

## Tech stack

| Layer | Technology |
| --- | --- |
| API / control plane | FastAPI, Pydantic, asyncpg (PostgreSQL) |
| Detection | Ultralytics YOLO |
| Tracking | ByteTrack (`trackers`, `supervision`) |
| Re-identification | Torch/TorchVision appearance embeddings, Milvus |
| Inference serving | NVIDIA Triton (gRPC) |
| Streaming | MediaMTX (RTSP / WebRTC / HLS), PyAV, FFmpeg |
| Messaging | Kafka (aiokafka) |
| Observability | Prometheus, Grafana, Loki, Alloy |
| Frontend | Next.js 16, React 19, Tailwind CSS, SWR |

## Repository layout

```
backend/
  src/
    opencv_pipeline/   edge detection/tracking/reid/identity pipeline
    core/               config, database, logging, exceptions
    routes/             camera, stream, health endpoints
    services/           camera, realtime video, tracking, presentation, inference
    observability/      Prometheus metrics, runtime + system collectors
  docs/                 architecture and pipeline documentation
  tests/                unit tests per service
  docker-compose.yaml   local infra: MediaMTX, Milvus, Kafka, Triton, Prometheus/Grafana
frontend/
  app/                  Next.js routes
  components/           dashboard, camera detail, stream views
  hooks/, store/, types/ client-side state and API types
```

## Getting started

### Prerequisites

- Python 3.10+, [uv](https://docs.astral.sh/uv/) (or `pip`)
- Node.js 20+
- Docker (for the local infrastructure stack)
- `ffmpeg` / `ffprobe` on `PATH`

### 1. Start local infrastructure

```bash
cd backend
docker compose up -d
```

This brings up MediaMTX, Milvus (+ etcd, MinIO), Kafka, Triton, Prometheus, and Grafana. PostgreSQL is **not** included in the compose file and must be provisioned separately — point `DATABASE_URL` at it.

### 2. Run the backend

```bash
cd backend
uv sync            # or: pip install -r requirements.txt
cp .env.example .env   # if present; otherwise set the variables below
uv run uvicorn src.main:app --reload
```

Key environment variables (see [`backend/src/core/config.py`](backend/src/core/config.py) for the full list): `DATABASE_URL`, `KAFKA_BOOTSTRAP_SERVERS`, `MEDIAMTX_*`, `TRACKING_*`, `TRACKING_IDENTITY_STORE_URI` (Milvus).

### 3. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Status

This is an actively developed platform, not a finished product. The control plane, camera/stream lifecycle, tracking, and identity resolution paths are implemented and covered by unit tests. The standalone Triton inference plane exists in code but is not yet fully wired into the FastAPI bootstrap — see [`backend/README.md`](backend/README.md) for the current, honest list of what's live versus in progress.
