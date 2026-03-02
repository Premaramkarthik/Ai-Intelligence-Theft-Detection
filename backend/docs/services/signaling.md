# Signaling Service: The External Interface

The **Signaling Service** acts as the dispatcher and management portal for the entire pipeline. It provides a FastAPI-powered gateway that bridges the internal Redis event bus with the outside world via REST and WebSockets.

---

## 1. Core Functions

- **State Management**: Provides a REST API for reading and writing live camera configurations (ROIs, thresholds) stored in Redis.
- **Real-Time Data Streaming**: Broadcasts JSON inference results to connected clients using standard WebSockets.
- **Binary Media Streaming**: Implements an MJPEG-over-WebSocket streamer for real-time visual monitoring.
- **Log Aggregation**: Collects logs from internal services and streams them live to a dedicated debug channel.

---

## 2. Live Communication (WebSockets)

Unlike conventional polling, the Signaling service maintains persistent connections to reduce latency and overhead.

- **`/ws/predictions`**: Subscribes to the global detection bus. Every time the `Inference` service identifies a person or an action, this channel broadcasts the result (BBoxes, labels, track IDs) instantly.
- **`/ws/camera/{cam_id}`**: Acts as a bridge between Shared Memory and the browser. It reads raw pixels from SHM, encodes them to JPEG, and sends them over the socket—perfect for live monitoring dashboards.
- **`/ws/logs`**: Streams system health events and worker status logs in real-time.

---

## 3. Technology Stack

- **FastAPI**: Asynchronous Python framework with built-in Pydantic v2 validation.
- **Redis Pub/Sub**: The backend engine for all real-time events.
- **Uvicorn**: High-performance ASGI server.
- **Pydantic**: Ensures that all API inputs (ROI updates) are valid before being pushed to the hardware workers.

---

## 🛠️ Operational Reference

### Startup Command (Local)
```bash
PYTHONPATH=. ./.venv/bin/python3 services/signaling/main.py
```

### Swagger UI
Detailed interactive documentation is available at:
`http://localhost:9000/docs`

---

## 💡 Notes on Authentication
While the service supports JWT-based security, it is currently configured for **Local Open Access** to facilitate rapid prototyping and testing without token management overhead.
