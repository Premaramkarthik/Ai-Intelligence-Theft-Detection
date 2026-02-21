# API Documentation

The Signaling Service provides a FastAPI-powered REST API and WebSocket interface for interacting with the Pipeline.

## Authentication
Most endpoints require a **JWT (JSON Web Token)**. Obtain a token by sending credentials to:
- `POST /auth/token`
- **Body**: `username`, `password` (Default: `admin`/`admin`)
- **Returns**: `access_token`

Add the token to your header: `Authorization: Bearer <token>`

---

## REST Endpoints

### 1. System Health
- **`GET /health`**
- **Description**: Returns the heartbeat status of all active components (Inference, MediaBridge).
- **Auth**: None

### 2. Camera Configuration
- **`GET /api/config/{camera_id}`**
- **Description**: Returns the current ROI, confidence thresholds, and input settings for a specific camera.
- **Auth**: JWT Required

- **`PUT /api/config/{camera_id}`**
- **Description**: Updates the camera settings live. Changes are pushed to Redis and picked up immediately by the relevant workers.
- **Body**: `ROI` (list of [x,y,w,h]), `thresholds` (object).
- **Auth**: JWT Required

### 3. Event History
- **`GET /api/events`**
- **Description**: Query historical detections from the database. Support filters for `camera_id`, `start_time`, and `end_time`.
- **Auth**: JWT Required

---

## WebSocket Interface

### Live Predictions Stream
- **URL**: `ws://<host>:<port>/ws/predictions`
- **Description**: A real-time stream of all detections and alerts.
- **Data Format**: 
```json
{
  "camera_id": "cam01",
  "detections": [...],
  "alerts": [...],
  "timestamp": 1708512345.123
}
```
- **Usage**: Typically used by the frontend to draw bounding boxes and status overlays on the video stream.

---

## API Design Principles
- **Asynchronous**: All handlers are `async def` to maximize concurrency.
- **Self-Documenting**: Visit `/docs` on the Signaling port (default 9000) for the interactive Swagger UI.
- **Standardized Errors**: All failure responses follow a JSON format with descriptive `detail` fields.
