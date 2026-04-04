import os

import cv2
import supervision as sv
from inference import get_model
from trackers import ByteTrackTracker

os.environ["CORE_MODEL_SAM3_ENABLED"] = "True"

model = get_model(model_id="rfdetr-medium")
tracker = ByteTrackTracker()

cap = cv2.VideoCapture("0")
while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    result = model.infer(frame)[0]
    detections = sv.Detections.from_inference(result)
    tracked = tracker.update(detections)