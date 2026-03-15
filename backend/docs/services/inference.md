# Inference Service

The inference service is standardized on two TensorRT engines only:

- `yolo26n.engine` for detection and tracking
- `cnn_transformer.engine` for temporal behavior classification

## Pipeline

1. Frames are read from shared memory.
2. `yolo26n.engine` detects people and items.
3. Interaction state determines whether a temporal clip should be classified.
4. `cnn_transformer.engine` classifies the clip.
5. Telemetry and incident events are published to Redis.

## Model Loading

- `ModelManager` loads exactly one detector and one classifier.
- Both models are required at startup.
- No legacy model formats or alternate-model fallback paths remain in the inference service.

## Configuration

Use these settings:

```bash
DETECTOR_ENGINE_PATH=models/yolo/yolo26n.engine
CLASSIFIER_ENGINE_PATH=models/shoplifting/cnn_transformer.engine
TEMPORAL_WINDOW=16
```
