# Project Architecture & Backend Documentation

## 1. Overall Architecture Overview

The Pipeline OpenCV project implements a **High-Performance Distributed Vision Pipeline**. It follows a **microservices-oriented architecture** where specialized services handle distinct stages of the video processing lifecycle.

### Design Principles
- **Modularity**: Every stage of the pipeline (capture, inference, signaling, persistence) is a standalone service.
- **Separation of Concerns**: Shared logic is strictly separated into `libs/`, while service-specific logic resides in `services/`.
- **Zero-Copy Performance**: Using **Shared Memory (SHM)** for video frame transport between capturing and inference processes to bypass serialization overhead and Python's GIL.
- **Asynchronous Event-Driven**: Services communicate via **Redis Pub/Sub** for live event streaming and **Redis Hash** for real-time configuration updates.

### Service Interaction
1. **MediaBridge**: Captures raw video from RTSP/Webcam, writes frames to SHM, and pushes frame pointers to Redis.
2. **Inference**: Consumes frame pointers, reads frames from SHM, runs AI models, and publishes detection events to Redis.
3. **Signaling**: Subscribes to Redis events to stream predictions via WebSockets and provides an API for system management.
4. **Alerting**: Monitors prediction events and dispatches notifications via Telegram/MQTT.
5. **Persistence**: Batches prediction events and persists them to the PostgreSQL database.

---

## 2. Detailed File & Folder Structure Breakdown

```text
.
├── docker/                 # Service-specific Dockerfiles
├── libs/                   # Shared business & infrastructure libraries
│   └── shared/             # The core internal library
│       ├── core/           # Settings management and base config
│       ├── logging/        # Unified structlog configuration
│       ├── shm/            # Shared Memory ring-buffer implementation
│       ├── types/          # Pydantic models for IPC messages
│       └── utils/          # Common helper functions
├── services/               # Independent service entry points
│   ├── alerting/           # Notification dispatcher (Telegram/MQTT)
│   ├── inference/          # AI Model execution (TensorRT/OpenVINO)
│   ├── mediabridge/        # Video capture & SHM management
│   ├── persistence/        # Database writer & event batching
│   └── signaling/          # WebSocket streaming & FastAPI management
├── scripts/                # Database initialization (SQL)
├── tests/                  # Pytest suite (Unit, Integration, E2E)
├── models/                 # AI Engines & Model weights
├── docker-compose.yml      # Multi-service orchestration
└── pyproject.toml          # Root package management
```

### Key Shared Modules
- **`libs.shared.core.settings`**: Centralized Pydantic-Settings module managing all environment variables.
- **`libs.shared.shm.ring_buffer`**: Low-level shared memory implementation using `multiprocessing.shared_memory`.
- **`libs.shared.logging.logger`**: Structured JSON logging across all services.

---

## 3. Technology Stack

| Layer | Technology | Justification |
| :--- | :--- | :--- |
| **Language** | Python 3.11 | Rapid development with excellent AI/Vision ecosystem. |
| **Video Processing** | OpenCV | Industry standard for hardware-accelerated video I/O. |
| **ML Inference** | TensorRT / OpenVINO | High-throughput AI execution on Edge/GPU hardware. |
| **API Framework** | FastAPI | Asynchronous performance with automatic OpenAPI documentation. |
| **Message Broker** | Redis | sub-millisecond latency for event streaming and IPC. |
| **Database** | PostgreSQL | Relational integrity for event logs and audit trails. |
| **Serialization** | Pydantic v2 | High-speed data validation and type safety. |
| **Containerization**| Docker / Compose | Consistent multi-service deployment. |

---

## 4. Setup & Usage

### Local Development
1. **Environment**: Copy `.env.example` to `.env` and fill in your credentials.
2. **Dependencies**: Run `make dev-install` to install the project in editable mode.
3. **Database**: The `persistence` service automatically initializes the database using `scripts/schema.sql` on startup.

### Running the System
- **Single Command**: `docker compose up -d`
- **Manual Debug**: `python -m services.<service_name>.main`

---

## 5. Security & Observability

### Security
- **JWT Authentication**: All Signaling API endpoints are protected via JSON Web Tokens.
- **Rate Limiting**: `slowapi` protects WebSocket and Token endpoints from brute-force/abuse.
- **Secrets**: Managed strictly via `.env` (excluded from Git).

### Observability
- **Structured Logging**: All logs are emitted in JSON format for easy ingestion by ELK/Loki.
- **Prometheus Metrics**: Each service exposes a `/metrics` endpoint (Ports 9100-9104) tracking capture rates, latency, and system health.

---

## 6. Testing Strategy

The project uses `pytest` with a dedicated `tests/` directory:
- **Unit Tests**: Test logic in `libs/` and individual service components.
- **Integration Tests**: Verify Redis IPC and Database persistence.
- **E2E Tests**: Mock camera input and verify the flow from MediaBridge to Signaling WebSockets.

Run tests: `make test`

---

## 8. Detailed Component Guides

For a deep dive into specific parts of the system, refer to these detailed guides:

- **Services**:
    - [MediaBridge](services/mediabridge.md) — Video Ingestion & SHM.
    - [Inference](services/inference.md) — AI Pipelines (D1-D5).
    - [Signaling](services/signaling.md) — API & WebSockets.
    - [Alerting](services/alerting.md) — Telegram & MQTT.
    - [Persistence](services/persistence.md) — Database & Evidence.
- **Core Library**:
    - [Shared Libraries](libs.md) — Settings, Logging, and IPC.
- **Interfaces**:
    - [API Reference](api.md) — REST & WebSocket endpoints.
- **Verification**:
    - [Testing Guide](testing_guide.md) — Automated & Manual procedures.
- **Ops**:
    - [Local Setup](local_setup.md) — Running without Docker.

---

## 9. How we are using the Backend

The backend is used as a **continuous monitoring engine**. It is designed to run 24/7 on edge hardware (like NVIDIA Jetson) or centralized GPU servers.

### 1. Data Flow Summary
1. Raw video enters via **MediaBridge**.
2. Intelligence is applied by **Inference**.
3. High-priority events are announced by **Alerting**.
4. All data is anchored by **Persistence**.
5. The outside world interacts via **Signaling**.

### 2. Operational Workflow
- **Admins** use the REST API to define security zones (ROIs) for each camera.
- **Security Teams** receive instant snapshots on Telegram when concealing behavior is detected.
- **Dashboards** connect via WebSockets to provide real-time visual feedback of the store floor.
- **Analysts** query the historical API to understand store traffic and theft trends over months.
