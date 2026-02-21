# Testing & Verification Guide

This guide details the procedures and tools available to verify the correctness, performance, and stability of the Pipeline OpenCV backend.

---

## 1. Real-Time Pipeline Inspection

Before running complex tests, use the **Inspector** tool to verify that data is flowing correctly through Redis and MQTT.

```bash
python3 scripts/inspect_data.py
```

### What it monitors:
- **Active Cameras**: Discovers which cameras are currently pushing frames.
- **Queue Backup**: Shows the current length of the `frames` queue in Redis (should stay near 0).
- **Processing Trends**: Shows if the system is catching up or falling behind.
- **MQTT Alerts**: Streams live JSON alerts from the `detections:*` channels.

---

## 2. Video-Based Integration Testing

To test the entire pipeline without a live RTSP stream, use the **Video Pipeline Test** script. This simulates `MediaBridge` by feeding a video file into the system.

```bash
PYTHONPATH=. ./.venv/bin/python3 tests/integration/test_video_pipeline.py --video "path/to/test_video.mp4"
```

### Key Features:
- **Frame Injection**: Automatically resizes and writes video frames into Shared Memory.
- **Metadata Simulation**: Pushes `FramePointer` messages to Redis just like a real camera worker.
- **Live Output**: Displays predictions (Person BBoxes, Action Labels) in the terminal as they are processed.
- **Verification**: Excellent for verifying that shoplifting triggers are correctly identified on recorded footage.

---

## 3. Latency Benchmarking

To measure the deterministic performance of the pipeline, use the **E2E Latency Validation** script.

```bash
python3 tests/integration/test_e2e_latency.py --camera cam01 --frames 200
```

### Metrics Reported:
- **p50 Latency**: Target < 60ms.
- **p95 Latency**: Target < 100ms.
- **p99 Latency**: Target < 150ms.
- **Packet Loss**: Monitors if any frames were "missed" by the inference service.

---

## 4. Manual Verification via Dashboard

For a visual "smoke test", use the Streamlit Dashboard.

1. Start all services: `./scripts/run_local.sh`.
2. Open: [http://localhost:8501](http://localhost:8501).
3. Connect to the Live Stream to see real-time bounding boxes and the background blur effect.

---

## 5. Automated Unit & Integration Tests

The project uses `pytest` for standard logic verification.

```bash
# Run all tests
make test

# Run specific service tests
pytest tests/integration/test_redis_transport.py
```
