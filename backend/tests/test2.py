from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import torch
from transformers import AutoModelForVideoClassification, AutoVideoProcessor

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.services.inference.contracts import InferenceIngressSample
from src.services.inference.temporal_buffer import TemporalBufferService
from src.services.realtime_video.contracts import StreamWorkerConfig
from src.services.realtime_video.frame_worker import PyAvFrameWorker
from src.services.realtime_video.queue import FrameQueue
from src.services.tracking.detectors.inference_detector import InferencePersonDetector
from src.services.tracking.trackers.bytetrack import RoboflowByteTrackPersonTracker
from src.utils.image import clamp_ltwh_to_frame, crop_ltwh

FRAMES_PER_CLIP = 16
SAMPLED_FRAMES = 8
INFER_INTERVAL = 0.5
MIN_STABLE_HITS = 4
MIN_CROP_WIDTH = 32
MIN_CROP_HEIGHT = 64
PREDICTION_TTL_SECONDS = 5.0

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
ID2LABEL = {"0": "non shop lifter", "1": "shop lifter"}

classifier = None
processor = None
shutdown_event = asyncio.Event()
executor = ThreadPoolExecutor(max_workers=4)

total_frames = 0
total_infers = 0
start_time = time.time()


@dataclass(slots=True)
class PredictionState:
    label: str
    confidence: float
    updated_at: float


def load_model(path: str | Path):
    path = str(Path(path).resolve())

    loaded_processor = AutoVideoProcessor.from_pretrained(path, local_files_only=True)
    loaded_model = AutoModelForVideoClassification.from_pretrained(
        path, trust_remote_code=True, local_files_only=True
    )

    loaded_model.to(DEVICE).eval()
    return loaded_model, loaded_processor


def sample_frames(frames):
    idx = np.linspace(0, len(frames) - 1, SAMPLED_FRAMES, dtype=int)
    return [frames[i] for i in idx]


def classify_clip(frames):
    global total_infers

    sampled = sample_frames(frames)
    video = np.stack(sampled)

    inputs = processor(video, return_tensors="pt")
    pixel_values = inputs["pixel_values_videos"].to(DEVICE)

    with torch.no_grad():
        outputs = classifier(pixel_values_videos=pixel_values)
        probs = torch.softmax(outputs.logits, dim=-1)
        pred = torch.argmax(probs, dim=-1).item()

    total_infers += 1
    return ID2LABEL[str(pred)], probs[0][pred].item()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "End-to-end RTSP/file smoke test that uses the backend PyAV stream worker, "
            "Roboflow detector, ByteTrack tracker, and the existing local classifier."
        )
    )
    parser.add_argument(
        "--source",
        default=os.getenv("TEST2_SOURCE"),
        help="RTSP URL or local video path. Can also be provided via TEST2_SOURCE.",
    )
    parser.add_argument(
        "--camera-id",
        default="cam_test2",
        help="Logical camera identifier used in frame and track metadata.",
    )
    parser.add_argument(
        "--stream-name",
        default="test2_stream",
        help="Logical stream name used in frame metadata.",
    )
    parser.add_argument(
        "--model-dir",
        default=str(
            BACKEND_ROOT / "model_repository" / "hf_vjepa2_finetune" / "best"
        ),
        help="Local Hugging Face classification model directory.",
    )
    parser.add_argument(
        "--sample-fps",
        type=float,
        default=8.0,
        help="Sampled frame rate for the PyAV frame worker.",
    )
    parser.add_argument(
        "--rtsp-transport",
        default="tcp",
        help="RTSP transport passed to PyAV when the source is an RTSP URL.",
    )
    parser.add_argument(
        "--detector-model-id",
        default="rfdetr-medium",
        help="Roboflow detector model ID.",
    )
    parser.add_argument(
        "--detector-confidence-threshold",
        type=float,
        default=0.45,
        help="Detector confidence threshold.",
    )
    parser.add_argument(
        "--detector-iou-threshold",
        type=float,
        default=0.35,
        help="Detector IoU threshold.",
    )
    parser.add_argument(
        "--detector-api-key",
        default=os.getenv("ROBOFLOW_API_KEY"),
        help="Optional Roboflow API key. Falls back to ROBOFLOW_API_KEY.",
    )
    parser.add_argument(
        "--tracker-lost-track-buffer",
        type=int,
        default=30,
        help="Roboflow tracker lost-track buffer.",
    )
    parser.add_argument(
        "--tracker-activation-threshold",
        type=float,
        default=0.45,
        help="Roboflow tracker activation threshold.",
    )
    parser.add_argument(
        "--tracker-minimum-consecutive-frames",
        type=int,
        default=3,
        help="Roboflow tracker minimum consecutive frames.",
    )
    parser.add_argument(
        "--tracker-minimum-iou-threshold",
        type=float,
        default=0.2,
        help="Roboflow tracker minimum IoU threshold.",
    )
    parser.add_argument(
        "--tracker-high-conf-det-threshold",
        type=float,
        default=0.5,
        help="Roboflow tracker high-confidence detection threshold.",
    )
    parser.add_argument(
        "--infer-interval",
        type=float,
        default=INFER_INTERVAL,
        help="Minimum seconds between classifications for the same track.",
    )
    parser.add_argument(
        "--display",
        action="store_true",
        help="Show the annotated output window.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Optional hard stop after N sampled frames. Zero means unlimited.",
    )
    parser.add_argument(
        "--open-timeout-seconds",
        type=float,
        default=8.0,
        help="PyAV open timeout in seconds.",
    )
    parser.add_argument(
        "--read-timeout-seconds",
        type=float,
        default=8.0,
        help="PyAV read timeout in seconds.",
    )
    parser.add_argument(
        "--max-reconnect-attempts",
        type=int,
        default=5,
        help="Frame worker reconnect limit.",
    )
    args = parser.parse_args()
    if not args.source:
        parser.error("--source is required unless TEST2_SOURCE is set.")
    return args


def _prepare_clip_crop(
    frame: np.ndarray,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
) -> np.ndarray | None:
    if width < MIN_CROP_WIDTH or height < MIN_CROP_HEIGHT:
        return None
    crop = crop_ltwh(frame, left, top, width, height)
    if crop is None:
        return None
    resized = cv2.resize(crop, (224, 224))
    return cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)


async def classify_identity_clip(
    identity_key: str,
    clip_frames: list[np.ndarray],
    *,
    loop: asyncio.AbstractEventLoop,
    predictions: dict[str, PredictionState],
    pending: set[str],
) -> None:
    try:
        label, confidence = await loop.run_in_executor(
            executor,
            classify_clip,
            clip_frames,
        )
        predictions[identity_key] = PredictionState(
            label=label,
            confidence=confidence,
            updated_at=time.time(),
        )
        print(f"[inference] {identity_key}: {label} ({confidence:.2f})")
    finally:
        pending.discard(identity_key)


def _draw_track_prediction(
    frame: np.ndarray,
    *,
    identity_key: str,
    left: int,
    top: int,
    width: int,
    height: int,
    confidence: float,
    prediction: PredictionState | None,
) -> None:
    label = prediction.label if prediction is not None else "Collecting..."
    score = prediction.confidence if prediction is not None else 0.0
    color = (0, 0, 255) if "shop" in label.lower() else (0, 255, 0)
    cv2.rectangle(frame, (left, top), (left + width, top + height), color, 2)
    cv2.putText(
        frame,
        f"{identity_key} | {label} {score:.2f} | det:{confidence:.2f}",
        (left, max(24, top - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        color,
        2,
        cv2.LINE_AA,
    )


def _prune_predictions(
    predictions: dict[str, PredictionState],
    *,
    active_track_ids: set[str],
    ttl_seconds: float = PREDICTION_TTL_SECONDS,
) -> None:
    now = time.time()
    stale = [
        track_id
        for track_id, prediction in predictions.items()
        if track_id not in active_track_ids and now - prediction.updated_at > ttl_seconds
    ]
    for track_id in stale:
        predictions.pop(track_id, None)


def print_logs() -> None:
    elapsed = time.time() - start_time
    fps = total_frames / elapsed if elapsed > 0 else 0
    ips = total_infers / elapsed if elapsed > 0 else 0

    print("\n========== RUN STATS ==========")
    print(f"Total Frames Processed : {total_frames}")
    print(f"Total Inferences       : {total_infers}")
    print(f"Elapsed Time (s)       : {elapsed:.2f}")
    print(f"FPS (stream)           : {fps:.2f}")
    print(f"IPS (inference/sec)    : {ips:.2f}")
    print("================================\n")


async def process_stream(args: argparse.Namespace) -> None:
    global total_frames

    frame_queue = FrameQueue(maxsize=64)
    frame_worker = PyAvFrameWorker(
        StreamWorkerConfig(
            camera_id=args.camera_id,
            stream_name=args.stream_name,
            mediamtx_rtsp_url=args.source,
            sample_fps=args.sample_fps,
            rtsp_transport=args.rtsp_transport,
            open_timeout_seconds=args.open_timeout_seconds,
            read_timeout_seconds=args.read_timeout_seconds,
            max_reconnect_attempts=args.max_reconnect_attempts,
        ),
        frame_queue,
    )
    worker_task = asyncio.create_task(frame_worker.run(), name="test2-frame-worker")

    detector = InferencePersonDetector(
        args.detector_model_id,
        confidence_threshold=args.detector_confidence_threshold,
        iou_threshold=args.detector_iou_threshold,
        target_class_name="person",
        api_key=args.detector_api_key,
    )
    tracker = RoboflowByteTrackPersonTracker(
        frame_rate=args.sample_fps,
        lost_track_buffer=args.tracker_lost_track_buffer,
        track_activation_threshold=args.tracker_activation_threshold,
        minimum_consecutive_frames=args.tracker_minimum_consecutive_frames,
        minimum_iou_threshold=args.tracker_minimum_iou_threshold,
        high_conf_det_threshold=args.tracker_high_conf_det_threshold,
    )
    temporal_buffer = TemporalBufferService(window_size=FRAMES_PER_CLIP, gap_reset_seconds=2.0)
    predictions: dict[str, PredictionState] = {}
    pending_inferences: set[str] = set()
    last_infer_started_at: dict[str, float] = {}
    loop = asyncio.get_running_loop()

    try:
        while not shutdown_event.is_set():
            sample = await frame_queue.consume()
            frame = sample.frame_array
            if frame is None:
                continue

            total_frames += 1
            detections = await loop.run_in_executor(executor, detector.detect, frame)
            tracks = tracker.update(detections)
            active_track_ids: set[str] = set()

            for track in tracks:
                left, top, width, height = clamp_ltwh_to_frame(
                    frame.shape[:2],
                    track.left,
                    track.top,
                    track.width,
                    track.height,
                )
                if width <= 0 or height <= 0:
                    continue

                identity_key = f"{args.camera_id}:{track.track_id}"
                active_track_ids.add(identity_key)
                clip_crop = _prepare_clip_crop(
                    frame,
                    left=left,
                    top=top,
                    width=width,
                    height=height,
                )

                if clip_crop is not None:
                    ingress = InferenceIngressSample(
                        camera_id=args.camera_id,
                        stream_name=args.stream_name,
                        local_track_id=track.track_id,
                        persistent_id=identity_key,
                        sampled_at=sample.sampled_at,
                        left=left,
                        top=top,
                        width=width,
                        height=height,
                        crop=clip_crop,
                        age_frames=track.age_frames,
                        consecutive_hits=track.consecutive_hits,
                        frames_since_update=track.frames_since_update,
                        persistent_id_state="assigned",
                    )
                    temporal_buffer.push(ingress)

                    ready_for_inference = (
                        temporal_buffer.depth(identity_key) >= FRAMES_PER_CLIP
                        and track.consecutive_hits >= MIN_STABLE_HITS
                        and track.frames_since_update == 0
                    )
                    cooled_down = (
                        time.time() - last_infer_started_at.get(identity_key, 0.0)
                        >= args.infer_interval
                    )
                    if (
                        ready_for_inference
                        and cooled_down
                        and identity_key not in pending_inferences
                    ):
                        clip_frames = [
                            item.crop for item in temporal_buffer.get(identity_key)
                        ]
                        pending_inferences.add(identity_key)
                        last_infer_started_at[identity_key] = time.time()
                        asyncio.create_task(
                            classify_identity_clip(
                                identity_key,
                                clip_frames,
                                loop=loop,
                                predictions=predictions,
                                pending=pending_inferences,
                            )
                        )

                _draw_track_prediction(
                    frame,
                    identity_key=identity_key,
                    left=left,
                    top=top,
                    width=width,
                    height=height,
                    confidence=track.confidence,
                    prediction=predictions.get(identity_key),
                )

            temporal_buffer.evict_stale(cutoff_seconds=2.0)
            _prune_predictions(predictions, active_track_ids=active_track_ids)

            if args.display:
                cv2.imshow("Tracker + Classification Test", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    shutdown_event.set()
                    break

            if args.max_frames and total_frames >= args.max_frames:
                shutdown_event.set()
                break
    finally:
        await frame_worker.stop()
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
        if args.display:
            cv2.destroyAllWindows()


async def main() -> None:
    global classifier
    global processor

    args = parse_args()
    print(f"Loading classification model from: {args.model_dir}")
    classifier, processor = load_model(args.model_dir)

    try:
        await process_stream(args)
    finally:
        print_logs()
        executor.shutdown(wait=True)


if __name__ == "__main__":
    asyncio.run(main())
