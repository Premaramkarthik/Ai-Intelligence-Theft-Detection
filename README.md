# Pipeline OpenCV — Real-Time Video Inference Pipeline

A Python-only, production-ready shoplifting detection pipeline using YOLOv8, ByteTrack, EfficientX3D, Telegram, and Redis.

## Project Structure

```
pipeline_opencv/
├── docs/                # Comprehensive technical documentation
├── libs/                # Shared business & infrastructure libraries
│   └── shared/          # Core internal library (logging, SHM, settings)
├── services/            # Independent service containers
│   ├── alerting/        # Telegram & MQTT alert dispatching
│   ├── inference/       # ML Pipeline (TensorRT/OpenVINO)
│   ├── mediabridge/     # Video capture & Shared Memory management
│   ├── persistence/     # DB worker (Automatic schema init)
│   └── signaling/       # WebSocket streaming & Management API
├── models/              # AI Engines & Model weights
├── docker/              # Service-specific Dockerfiles
├── scripts/             # Database initialization (schema.sql)
├── tests/               # Pytest suite (Unit, Integration, E2E)
├── docker-compose.yml   # Multi-service orchestration
├── .env.example         # Configuration template
└── pyproject.toml       # Root package management
```

See [Backend Architecture](docs/backend_architecture.md) for a deep dive or [Local Setup](docs/local_setup.md) for non-docker instructions.

## Quick Start

### 1. Environment Setup

```bash
cp .env.example .env
# Edit .env with your Redis password, Telegram token, etc.
```

### 2. Quantize Your Models (one-time, do before running inference)

```bash
pip install -r model_quantization/requirements.txt

# Quantize EfficientX3D to TensorRT FP16 (recommended)
python model_quantization/scripts/quantize.py --model efficient_x3d --backend tensorrt --precision fp16

# For CPU-only (MoViNet → OpenVINO)
python model_quantization/scripts/quantize.py --model movinet --backend openvino --precision int8
```

### 3. Start Infrastructure

```bash
docker compose up redis postgres mqtt -d
```

### 4. Apply DB Schema

```bash
psql -h localhost -U pipeline_user -d pipeline_events -f scripts/schema.sql
```

### 5. Start All Services

```bash
# Option A: Docker (recommended)
docker compose up --build

# Option B: Manual (dev mode)
python backend/mediabridge/main.py &
python backend/inference/main.py &
python backend/alerting/main.py &
python backend/persistence/main.py &
uvicorn backend.signaling.main:app --host 0.0.0.0 --port 9000
```

## Detection Pipeline

| Stage | Component | Description |
|---|---|---|
| D1 | `PersonDetector` | YOLOv8n-seg — person bbox + segmentation mask |
| D2 | `BackgroundBlur` | Gaussian blur on inverse seg mask |
| D3 | `PersonTracker` | ByteTrack — stable `track_id` across frames |
| D4 | `ItemInteractionDetector` | IDLE→WATCHING→TRIGGERED state machine |
| D5 | `TriggeredClassifier` | EfficientX3D inference on 16-frame window |

## API Endpoints (Signaling Service)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/token` | — | Get JWT token |
| `GET` | `/health` | — | Inference heartbeat status |
| `GET` | `/api/config/{camera_id}` | JWT | Read camera config |
| `PUT` | `/api/config/{camera_id}` | JWT | Update ROI / thresholds live |
| `WS` | `/ws/predictions` | — | Live predictions stream |

## Environment Variables

See [`.env.example`](.env.example) for all variables with descriptions.

## Code Quality

```bash
# Lint + format
ruff check libs/ services/ --fix && ruff format libs/ services/

# Static analysis (must score ≥ 8.5)
pylint libs/ services/ --rcfile=.pylintrc --fail-under=8.5

# Install pre-commit hooks
pre-commit install
```

## Adding More Cameras

1. Add `CAM03_INPUT_TYPE`, `CAM03_RTSP_URL` etc. to `.env`
2. Set `NUM_CAMERAS=3`
3. Run: `psql … -c "HSET config:cam03 roi '[0,0,1280,720]' threshold 0.7"`
4. Restart MediaBridge and Inference (they auto-discover new camera count)

## Future: Frontend

The `frontend/` directory is reserved. When you're ready:
- Drop in a Next.js or Vite project there.
- The Signaling service already mounts it at `/ui`.
- The `/ws/predictions` WebSocket provides the live feed.
- Consider enabling the Nginx block in `docker-compose.yml` for TLS.
