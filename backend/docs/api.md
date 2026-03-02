# API Reference

The **Signaling Service** provides a FastAPI-powered REST API and WebSocket interface for system management and real-time data streaming.

---

## 🚀 Interactive Documentation
Visit the Swagger UI on your local deployment for a full interactive reference:
- **URL**: `http://localhost:9000/docs`

---

## 🛠️ REST Endpoints

### 1. System Health
- **`GET /health`**
- **Description**: Returns the heartbeat status of the inference engine and active camera workers.

### 2. Camera Configuration
- **`GET /api/config/{camera_id}`**
- **Description**: Retrieves the current ROI (Region of Interest), confidence thresholds, and interaction parameters for a camera.
- **`PUT /api/config/{camera_id}`**
- **Description**: Updates camera settings live. Changes are written to Redis and picked up immediately by `Inference` and `MediaBridge`.
- **Payload**:
  ```json
  {
    "roi": {"x": 0, "y": 0, "w": 1280, "h": 720},
    "confidence_threshold": 0.5,
    "enabled": true
  }
  ```

### 3. Historical Events
- **`GET /api/events`**
- **Description**: Query the PostgreSQL database for historical shoplifting alerts and interaction events.

---

## 📡 WebSocket Interface

The system uses WebSockets for high-frequency data (predictions) and binary media (camera streams).

### 1. Live Predictions Stream
- **URL**: `ws://localhost:9000/ws/predictions`
- **Description**: Broadcasts a unified stream of detections from all cameras.
- **Payload Format**:
  ```json
  {
    "camera_id": "cam01",
    "ts": 1708512345.678,
    "detections": [
      {"bbox": [100, 200, 300, 400], "label": "person", "track_id": 42}
    ],
    "action": {"label": "shoplifting", "confidence": 0.92}
  }
  ```

### 2. Live Camera Stream (MJPEG)
- **URL**: `ws://localhost:9000/ws/camera/{camera_id}`
- **Description**: Streams a live MJPEG video feed for a specific camera. Useful for dashboards that don't support RTSP directly.

### 3. Log Stream
- **URL**: `ws://localhost:9000/ws/logs`
- **Description**: A real-time stream of system-wide logs (JSON format) filtered from the `inference` and `mediabridge` services.

---

## 💡 Notes
- **Authentication**: Authentication is currently optional/disabled for local deployment to simplify development. 
- **CORS**: The API is configured to allow connections from common frontend dev ports (3000, 5173, 8501).
