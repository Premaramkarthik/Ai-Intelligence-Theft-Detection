"""
Video Pipeline Test Script
==========================
Feeds a video file into the inference pipeline via Shared Memory and Redis.
Measures latency and prints detections in real-time.

USAGE:
  python tests/integration/test_video_pipeline.py --video path/to/video.mp4 --camera cam01
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid

# Add project root to path so 'libs' is found
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import cv2
import numpy as np
import redis.asyncio as aioredis
from dotenv import load_dotenv

from libs.shared.shm.ring_buffer import RingBufferWriter
from libs.shared.types.models import FramePointer

load_dotenv()

async def run_video_test(video_path: str, camera_id: str, limit: int, fps_cap: float):
    # 1. Setup Redis
    redis_url = (
        f"redis://:{os.getenv('REDIS_PASSWORD', 'karthikS9')}@"
        f"{os.getenv('REDIS_HOST', 'localhost')}:"
        f"{os.getenv('REDIS_PORT', '6379')}/0"
    )
    redis = aioredis.from_url(redis_url, decode_responses=True)

    # 2. Setup SHM Writer (to simulate MediaBridge)
    # We assume the standard frame size 720x1280 for the pipeline
    writer = RingBufferWriter(camera_id, num_slots=32, frame_height=720, frame_width=1280)
    
    # 3. Open Video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Could not open video: {video_path}")
        return

    print(f"\n🚀 Starting Video Pipeline Test")
    print(f"📂 Video: {video_path}")
    print(f"📸 Camera: {camera_id}")
    print(f"{'='*60}\n")

    # 4. Background Listener for detections
    async def listener():
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"detections:{camera_id}")
        print(f"📡 Listening for predictions on 'detections:{camera_id}'...")
        try:
            async for msg in pubsub.listen():
                if msg['type'] == 'message':
                    try:
                        data = json.loads(msg['data'])
                        elapsed = (time.time() - data['ts']) * 1000
                        det_count = len(data.get('detections', []))
                        action = data.get('action')
                        action_str = f" | Action: {action['label']} ({action['confidence']:.2f})" if action else ""
                        print(f"📥 Recv {data['camera_id']} | {det_count} dets{action_str} | Latency: {elapsed:.1f}ms")
                    except Exception:
                        pass
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    listener_task = asyncio.create_task(listener())
    
    frame_count = 0
    start_time = time.perf_counter()
    
    try:
        while cap.isOpened() and (limit == 0 or frame_count < limit):
            ret, frame = cap.read()
            if not ret:
                break

            # Resize to pipeline resolution if needed
            if frame.shape[0] != 720 or frame.shape[1] != 1280:
                frame = cv2.resize(frame, (1280, 720))

            t_capture = time.time()
            trace_id = str(uuid.uuid4())

            # A. Write to SHM
            slot_id = writer.write(frame)

            # B. Push metadata to Redis
            ptr = FramePointer(
                camera_id=camera_id,
                slot_id=slot_id,
                t_capture=t_capture,
                trace_id=trace_id
            )
            await redis.lpush("frames", ptr.to_bytes())

            if (frame_count + 1) % 10 == 0:
                print(f"� Sent {frame_count+1} frames...")

            frame_count += 1
            
            # Cap FPS
            if fps_cap > 0:
                elapsed_loop = time.perf_counter() - start_time
                target_time = frame_count / fps_cap
                sleep_time = target_time - elapsed_loop
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        print(f"\nWaiting 5s for remaining predictions...")
        await asyncio.sleep(5)

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        cap.release()
        listener_task.cancel()
        writer.close()
        await redis.aclose()
        print(f"\n✅ Finished. Processed {frame_count} frames.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, help="Path to video file")
    parser.add_argument("--camera", default="cam01", help="Target camera ID")
    parser.add_argument("--limit", type=int, default=0, help="Max frames to process (0=all)")
    parser.add_argument("--fps", type=float, default=10.0, help="Max injection FPS (default 10)")
    args = parser.parse_args()

    asyncio.run(run_video_test(args.video, args.camera, args.limit, args.fps))

if __name__ == "__main__":
    main()
