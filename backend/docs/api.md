# API Reference

The **Signaling Service** provides a FastAPI-powered REST API and WebSocket interface for system management, real-time data streaming, and hardware monitoring.

---

## 🚀 Interactive Documentation
Visit the Swagger UI on your local deployment for a full interactive reference:
- **URL**: `http://localhost:9001/docs`

---

## 🛠️ REST Endpoints

### 1. System Monitoring
- **`GET /api/status`**
- **Description**: Returns real-time health metrics including:
  - **GPU**: VRAM usage, utilization %, and temperature.
  - **Redis**: Connection status ping.
  - **Cameras**: Count of total configured vs. active streaming sources.
  - **System**: CPU/RAM load.

### 2. Camera Management
- **`POST /api/camera/connect`**
- **Description**: Dynamically adds a new camera source (Webcam or RTSP).
- **Payload (Webcam)**:
  ```json
  {"source_type": "webcam"}
  ```
- **Payload (RTSP)**:
  ```json
  {
    "source_type": "rtsp",
    "rtsp_config": {
      "rtsp_url": "rtsp://admin:password@192.168.1.100:554/stream1"
    }
  }
  ```

- **`GET /api/cameras`**
- **Description**: Lists all currently registered camera IDs and their sources.

- **`DELETE /api/cameras/{camera_id}`**
- **Description**: Safely disconnects a camera and cleans up its Redis configuration and frame pointers.

### 3. Live Configuration
- **`GET /api/config/{camera_id}`**
- **Description**: Retrieves ROI, confidence thresholds, and interaction metadata.
- **`PUT /api/config/{camera_id}`**
- **Description**: Updates camera parameters live without service restart.

### 4. Historical Events
- **`GET /api/events`**
- **Description**: Query the PostgreSQL database for historical shoplifting alerts.

---

## 📡 WebSocket Interface

### 1. Live Predictions Stream
- **URL**: `ws://localhost:9001/ws/predictions`
- **Payload**:
  ```json
  {
    "camera_id": "cam01",
    "ts": 1708512345.678,
    "detections": [...],
    "action": {"label": "shoplifting", "confidence": 0.92}
  }
  ```

### 2. Live Camera Preview (MJPEG)
- **URL**: `ws://localhost:9001/ws/camera/{camera_id}`
- **Description**: Dedicated binary stream for browser-native video preview.

---

## 💡 Notes
- **Hardware Agnostic**: The Status API works with or without NVIDIA GPUs (falls back gracefully).
- **Persistence**: Camera configurations are persisted in Redis and indexed by unique `camera_id`.
