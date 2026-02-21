# Inference Service

The **Inference Service** is the "brain" of the pipeline. It executes complex AI models at high speed to detect people, track their movements, and identify suspicious interactions.

## Purpose
- Process video frames at 15-30 FPS per camera.
- Detect people and segment them from the background.
- Track unique individuals across time.
- Identify shoplifting interactions (e.g., reaching for an item, concealing).

## Technologies Used
- **TensorRT**: NVIDIA's high-performance deep learning inference optimizer and runtime. Many models are quantized to FP16 for maximum GPU throughput.
- **OpenVINO**: Intel's toolset for optimizing and deploying AI inference on CPUs and integrated GPUs.
- **YOLOv8-seg**: Used for real-time person detection and segmentation.
- **ByteTrack**: A simple yet effective association algorithm that tracks objects by associating almost every detection box instead of only high-score ones.
- **EfficientX3D**: A state-of-the-art spatio-temporal model designed for efficient video classification.

## The Pipeline Stages (D1-D5)
1. **D1: Person Detection**: YOLOv8 segments persons in the frame.
2. **D2: Privacy Blur**: (Optional) Blurs the background or non-tracked persons for privacy compliance.
3. **D3: Tracking**: ByteTrack assigns a persistent `track_id` to each person.
4. **D4: Interaction Detection**: A state machine monitors the proximity of tracked persons to defined regions-of-interest (ROIs) or items.
5. **D5: Action Recognition**: If a suspicious interaction is triggered, a 16-frame window is sent to the EfficientX3D model for behavior classification (e.g., "Normal" vs "Concealing").

## Performance Optimization
- **Zero-Copy**: Reads frames directly from Shared Memory allocated by MediaBridge.
- **Batched Inference**: Can be configured to batch frames from multiple cameras for improved GPU utilization.
