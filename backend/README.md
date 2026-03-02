# Pipeline OpenCV — Real-Time Video Inference Pipeline

A high-performance, production-ready shoplifting detection pipeline using YOLOv8, ByteTrack, EfficientX3D, and Redis.

## Project Structure (Monorepo)

```text
pipeline_opencv/
├── apps/
│   └── dashboard/           # Streamlit UI  (pyproject.toml + Dockerfile)
│       └── src/dashboard/
│           ├── pages/
│           └── components/
├── services/                # Independent backend microservices
│   ├── signaling/           # WebSocket + REST API  (FastAPI)
│   ├── mediabridge/         # RTSP ingestion + SHM transport
│   ├── inference/           # GPU AI pipeline  (TensorRT/ONNX)
│   ├── alerting/            # Telegram + MQTT dispatch
│   └── persistence/         # PostgreSQL async writer
├── packages/
│   └── shared/              # Internal shared library (pip install -e)
│       └── src/shared/      # SHM utils, logging, types, DB
├── data/
│   └── samples/             # Local test videos only
├── research/
│   └── notebooks/           # Exploratory notebooks (not imported by services)
├── models/                  # AI weight artifacts (use DVC / S3 in prod)
├── scripts/                 # run_local.sh, cleanup.sh, inspect_data.py
├── docker/                  # Per-service Dockerfiles
├── docs/                    # ADRs + per-service guides
├── tests/                   # Cross-service integration & E2E tests
├── docker-compose.yml       # Full-stack local orchestration
├── pyproject.toml           # Root: workspace-level linting (Ruff, Mypy)
└── Makefile
```

See [Backend Architecture](docs/backend_architecture.md) for a deep dive or [Testing Guide](docs/testing_guide.md) for verification.

## Quick Start

### 1. Environment Setup

```bash
cp .env.example .env
# Edit .env with your Redis settings, model paths, etc.
```

### 2. Start Project (Automatic)

The easiest way to start everything locally (Redis, MQTT, and all Python services) is:

```bash
./scripts/run_local.sh
```

### 3. Start Manually (Infrastructure Only)

If you want to run services in your debugger:

```bash
# Start Docker infra
docker compose up redis postgres mqtt -d

# Start services individually (requires ./.venv)
./.venv/bin/python3 services/mediabridge/main.py
./.venv/bin/python3 services/inference/main.py
./.venv/bin/python3 services/signaling/main.py
./.venv/bin/streamlit run app.py
```

## Detection Pipeline

| Stage | Component | Description |
|---|---|---|
| D1 | `PersonDetector` | YOLOv8n-seg — person bbox + segmentation mask |
| D2 | `BackgroundBlur` | Optimized Gaussian blur on inverse mask |
| D3 | `PersonTracker` | IOU-based tracker for stable `track_id` |
| D4 | `ItemInteractionDetector` | Proximity-based interaction state machine |
| D5 | `TriggeredClassifier` | **Async** EfficientX3D classification on 16-frame window |

## API Endpoints (Signaling Service)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | System heartbeat & worker status |
| `GET` | `/api/config/{camera_id}` | — | Read camera ROI/thresholds |
| `PUT` | `/api/config/{camera_id}` | — | Update configuration live |
| `WS` | `/ws/predictions` | — | Live detections stream (JSON) |
| `WS` | `/ws/camera/{camera_id}` | — | MJPEG live camera stream |

## Verification Tools

| Tool | Command | Purpose |
|---|---|---|
| **Inspector** | `python3 scripts/inspect_data.py` | Live terminal dashboard for Redis/MQTT |
| **Video Test** | `python3 tests/integration/test_video_pipeline.py` | Feed a video file into the pipeline |
| **Latency** | `python3 tests/integration/test_e2e_latency.py` | Benchmarking frame-to-prediction speed |

## Operations

- **Automatic Seeding**: MediaBridge automatically seeds default ROI and thresholds into Redis on startup if they don't exist.
- **Lag Prevention**: Inference service automatically drains its queue if a backlog > 100 frames is detected to maintain real-time parity.
- **Dashboard**: Use the Streamlit dashboard at `http://localhost:8501` for a visual overview.
