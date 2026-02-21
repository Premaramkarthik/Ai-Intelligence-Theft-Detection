# Testing Guide

This document explains how to verify the correctness and performance of the Pipeline OpenCV backend.

## 1. Automated Testing

The project uses `pytest` for automated testing.

### Running All Tests
To run all available tests, use the Makefile shortcut:
```bash
make test
```
Or run pytest directly:
```bash
pytest tests/
```

### Types of Tests
- **E2E Tests (`tests/e2e/`)**: These tests simulate the entire flow from capture to prediction output. For example, `test_e2e_latency.py` measures the total time a frame takes to travel through the pipeline.
- **Unit Tests**: (Under development) These verify individual logic components in `libs/` and `services/`.
- **Integration Tests**: Verify connections to Redis and PostgreSQL.

---

## 2. Manual Functional Verification

### A. API & System Health (Swagger UI)
FastAPI automatically generates an interactive documentation page.
1. Ensure the system is running: `docker compose up -d`.
2. Open your browser to: [http://localhost:9000/docs](http://localhost:9000/docs)
3. **Smoke Test**:
   - Use the `/auth/token` endpoint to log in (default: `admin`/`admin`).
   - Copy the `access_token`.
   - Click "Authorize" at the top and paste the token.
   - Try the `GET /health` endpoint; it should return `status: healthy` and show active camera workers.

### B. Live Predictions (WebSockets)
To verify that the inference engine is actually detecting objects:
1. Use a WebSocket client (like Chrome's "Simple WebSocket Client" extension or Postman).
2. Connect to `ws://localhost:9000/ws/predictions`.
3. If a camera is active, you should see a stream of JSON messages containing detection coordinates and track IDs.

### C. Database Verification (pgAdmin)
1. Open [http://localhost:5050](http://localhost:5050).
2. Login with your `.env` credentials.
3. Query the `events` table:
   ```sql
   SELECT * FROM events ORDER BY timestamp DESC LIMIT 10;
   ```
4. You should see entries appearing as detections occur.

### D. Alerting Verification (Telegram)
1. Trigger a high-confidence event (e.g., place a watched item in a person's bag if testing with a live camera).
2. Check your configured Telegram chat.
3. You should receive a summary message with the confidence score and camera ID.

---

## 3. Simulating Camera Input for Testing
If you don't have a real RTSP camera or webcam attached:
1. Prepare a short `.mp4` video file.
2. Update your `.env`:
   ```bash
   CAMERA_SOURCES=/path/to/your/video.mp4
   ```
3. Restart the `mediabridge` service: `docker compose restart mediabridge`.
4. The pipeline will treat the video file as a live stream, allowing you to test the inference and alerting logic without physical hardware.

---

## 4. Performance Benchmarking
Check the Prometheus metrics for bottlenecks:
- **Signaling Metrics**: [http://localhost:9100/metrics](http://localhost:9100/metrics)
- **Inference Metrics**: [http://localhost:9101/metrics](http://localhost:9101/metrics)
- **Capture Metrics**: [http://localhost:9102/metrics](http://localhost:9102/metrics)

### E. Streamlit Test Dashboard (Easiest)
For a visual way to check health and monitor stream:
1. Run: `streamlit run app.py`
2. Open the URL shown in terminal (default: [http://localhost:8501](http://localhost:8501)).
3. Login with `admin`/`admin` in the sidebar.
4. Toggle "Start Live Monitor" to see detections in real-time.
