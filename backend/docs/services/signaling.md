# Signaling Service: The External Interface

The **Signaling Service** is the central nervous system for external communication. It acts as a FastAPI-powered gateway that bridges internal high-performance events with user-facing dashboards and management tools.

---

## 1. Core Functions

- **Dynamic Orchestration**: Provides the `/api/camera/connect` gateway, allowing users to add hardware sources (Webcam/RTSP) at runtime without restarting the pipeline.
- **Unified Health Monitoring**: Houses the `/api/status` engine which provides real-time telemetry on GPU power, Redis connectivity, and active ingestion workers.
- **Real-Time Data Streaming**: Broadcasts live detection results and action labels via WebSockets.
- **Binary Media Streaming**: Encodes and streams raw pixels from Shared Memory to browser-friendly MJPEG feeds.

---

## 2. Live Communication (WebSockets)

Signaling maintains persistent connections to eliminate polling latency:

- **`/ws/predictions`**: The primary data feed. Broadcasts every person's bounding box, track ID, and classified actions (e.g., "shoplifting") as they happen.
- **`/ws/camera/{cam_id}`**: The vision feed. Reads raw BGR pixels from Shared Memory, performs high-speed JPEG encoding, and delivers a binary stream to the frontend.
- **`/ws/logs`**: Delivers a JSON log stream for real-time debugging of worker activities and inference performance.

---

## 3. Hardware Monitoring (Status API)

The service provides a critical link for hardware visibility. The `/status` endpoint aggregates:
-   **Nvidia NVML Data**: GPU memory utilization, clock speeds, and temperatures.
-   **CPU/System Load**: Real-time awareness of RAM and processing overhead.
-   **Service Topology**: Sync check between configured cameras in Redis and active worker tasks in MediaBridge.

---

## 4. Technology Stack

- **FastAPI**: Asynchronous gateway for high-concurrency WebSocket management.
- **Pydantic v2**: Strict schema validation for all incoming configuration updates.
- **Redis Pub/Sub & Hashes**: Used as the low-latency state store and event bus.

---

## 🛠️ Management
Detailed interactive documentation and testing playground are available locally:
- **Swagger UI**: `http://localhost:9000/docs`
- **ReDoc**: `http://localhost:9000/redoc`
