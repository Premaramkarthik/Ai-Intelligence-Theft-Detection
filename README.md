# Pipeline OpenCV — Real-Time Video Inference Pipeline

A high-performance, production-ready shoplifting detection pipeline using YOLOv8, ByteTrack, EfficientX3D, and Redis.

## Project Structure

```text
pipeline_opencv/
├── docs/                # Comprehensive technical documentation
├── libs/                # Shared business & infrastructure libraries
│   └── shared/          # Core internal library (logging, SHM, types)
├── services/            # Independent service containers
│   ├── alerting/        # Telegram & MQTT alert dispatching
│   ├── inference/       # ML Pipeline (TensorRT/OpenVINO)
│   ├── mediabridge/     # Video capture & Shared Memory management
│   ├── persistence/     # DB worker (Automatic schema init)
│   └── signaling/       # WebSocket streaming & Management API
├── models/              # AI Engines & Model weights
├── scripts/             # Startup, inspection, and DB scripts
├── tests/               # Pytest suite & latency benchmarks
├── docker-compose.yml   # Multi-service orchestration
├── .env.example         # Configuration template
└── pyproject.toml       # Root package management
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
