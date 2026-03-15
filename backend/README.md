# Pipeline OpenCV Backend

Real-time video inference pipeline built around two fixed inference engines:

- `models/yolo/yolo26n.engine` for object detection and tracking
- `models/shoplifting/cnn_transformer.engine` for behavior classification

## Backend Services

- `services/mediabridge`: frame ingestion and shared-memory publishing
- `services/inference`: GPU inference pipeline
- `services/signaling`: REST and WebSocket API
- `services/alerting`: Telegram and MQTT dispatch
- `services/persistence`: PostgreSQL event storage

## Inference Pipeline

| Stage | Component | Description |
|---|---|---|
| D1 | `ObjectDetector` | Runs `yolo26n.engine` for person and item detection |
| D2 | `ItemInteractionDetector` | Tracks proximity and interaction state |
| D3 | `BehaviorClassifier` | Runs `cnn_transformer.engine` on temporal clips |
| D4 | Event emission | Publishes telemetry and incidents |

## Local Configuration

Set the engine paths with:

```bash
DETECTOR_ENGINE_PATH=models/yolo/yolo26n.engine
CLASSIFIER_ENGINE_PATH=models/shoplifting/cnn_transformer.engine
```
