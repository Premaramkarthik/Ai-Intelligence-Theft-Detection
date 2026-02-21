"""
End-to-End Latency Validation Script
=====================================
Measures pipeline latency from frame capture → inference output.
Target: p50 < 60ms, p95 < 100ms, p99 < 150ms

HOW IT WORKS:
  1. Writes a synthetic frame into SHM ring buffer (simulates MediaBridge).
  2. Pushes a FramePointer onto the Redis `frames_meta` stream.
  3. Listens on the `predictions` stream for the corresponding trace_id.
  4. Measures wall-clock RTT and reports percentiles.

USAGE (with inference service running):
  python tests/integration/test_e2e_latency.py --camera cam01 --frames 200 --warmup 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import uuid
from dataclasses import dataclass, field

import numpy as np
import redis.asyncio as aioredis
from dotenv import load_dotenv
import os

load_dotenv()

STREAM_KEY = "frames_meta"
PREDICTIONS_STREAM = "predictions"
STREAM_MAXLEN = 500
TIMEOUT_S = 5.0          # max wait per frame before marking as MISS


@dataclass
class LatencyResult:
    trace_id: str
    t_send_ns: int
    t_recv_ns: int | None = None

    @property
    def latency_ms(self) -> float | None:
        if self.t_recv_ns is None:
            return None
        return (self.t_recv_ns - self.t_send_ns) / 1e6


def _build_synthetic_frame(h: int = 720, w: int = 1280, c: int = 3) -> np.ndarray:
    """Random BGR frame — exercises the full pixel path through SHM."""
    rng = np.random.default_rng()
    return rng.integers(0, 256, (h, w, c), dtype=np.uint8)


async def inject_frame(
    redis: aioredis.Redis,
    camera_id: str,
    slot_id: int,
    trace_id: str,
    shape: list[int],
) -> int:
    """Push a FramePointer to Redis Stream. Returns t_capture in ns."""
    t_capture = time.perf_counter_ns()
    shm_name = f"cam_{camera_id}_ring"
    await redis.xadd(
        STREAM_KEY,
        {
            "camera_id": camera_id,
            "slot_id": str(slot_id),
            "shm_name": shm_name,
            "shape": json.dumps(shape),
            "dtype": "uint8",
            "t_capture": str(t_capture),
            "trace_id": trace_id,
        },
        maxlen=STREAM_MAXLEN,
        approximate=True,
    )
    return t_capture


async def wait_for_prediction(
    redis: aioredis.Redis, trace_id: str, last_id: str
) -> tuple[str | None, str]:
    """
    Poll Redis `predictions` stream for an entry matching trace_id.
    Returns (received_trace_id, new_last_id) or (None, last_id) on timeout.
    """
    deadline = asyncio.get_event_loop().time() + TIMEOUT_S
    while asyncio.get_event_loop().time() < deadline:
        messages = await redis.xread(
            {PREDICTIONS_STREAM: last_id}, count=20, block=100
        )
        for _, entries in messages or []:
            for msg_id, data in entries:
                last_id = msg_id
                found_trace = data.get(b"trace_id", b"").decode()
                if found_trace == trace_id:
                    return trace_id, last_id
    return None, last_id


async def run_latency_test(
    camera_id: str,
    num_frames: int,
    warmup: int,
    fps_cap: float,
) -> None:
    """Main test loop. Injects frames and collects latencies."""
    redis_url = (
        f"redis://:{os.getenv('REDIS_PASSWORD', '')}@"
        f"{os.getenv('REDIS_HOST', 'localhost')}:"
        f"{os.getenv('REDIS_PORT', '6379')}/"
        f"{os.getenv('REDIS_DB', '0')}"
    )
    redis = aioredis.from_url(redis_url, decode_responses=False)

    shape = [720, 1280, 3]
    frame = _build_synthetic_frame()

    # Allocate SHM ring buffer so Inference can read the frame
    import multiprocessing.shared_memory as mp_shm
    shm_name = f"cam_{camera_id}_ring"
    num_slots = int(os.getenv("SHM_SLOTS_PER_CAM", "32"))
    frame_bytes = int(np.prod(shape))
    try:
        shm = mp_shm.SharedMemory(name=shm_name, create=True, size=num_slots * frame_bytes)
    except FileExistsError:
        shm = mp_shm.SharedMemory(name=shm_name, create=False)

    # Write synthetic frame to slot 0
    buf = np.ndarray(shape, dtype=np.uint8, buffer=shm.buf, offset=0)
    np.copyto(buf, frame)

    print(f"\n{'='*60}")
    print(f"  E2E Latency Test — camera: {camera_id}")
    print(f"  Frames: {num_frames}  |  Warmup: {warmup}  |  FPS cap: {fps_cap}")
    print(f"{'='*60}\n")

    results: list[LatencyResult] = []
    frame_interval = 1.0 / fps_cap
    last_pred_id = "$"
    misses = 0

    total_frames = warmup + num_frames

    for i in range(total_frames):
        trace_id = str(uuid.uuid4())
        t_send = await inject_frame(redis, camera_id, 0, trace_id, shape)
        result = LatencyResult(trace_id=trace_id, t_send_ns=t_send)

        found, last_pred_id = await wait_for_prediction(redis, trace_id, last_pred_id)
        if found:
            result.t_recv_ns = time.perf_counter_ns()
        else:
            misses += 1

        if i >= warmup and result.latency_ms is not None:
            results.append(result)
            lat = result.latency_ms
            status = "✅" if lat < 100 else ("⚠️ " if lat < 150 else "❌")
            if (i - warmup) % 20 == 0:
                print(f"  Frame {i - warmup + 1:>4}/{num_frames} | {status} {lat:>7.1f} ms | trace: {trace_id[:8]}…")

        await asyncio.sleep(max(0.0, frame_interval - 0.01))

    # ── Report ────────────────────────────────────────────────────────────────
    latencies = [r.latency_ms for r in results if r.latency_ms is not None]
    if not latencies:
        print("\n  ❌ No results received — is the inference service running?")
        return

    sorted_l = sorted(latencies)
    n = len(sorted_l)
    p50 = statistics.median(latencies)
    p95 = sorted_l[int(0.95 * n)]
    p99 = sorted_l[int(0.99 * n)]
    mean = statistics.mean(latencies)
    mx = max(latencies)

    print(f"\n{'='*60}")
    print("  RESULTS")
    print(f"{'='*60}")
    print(f"  Frames measured : {n}  |  Misses: {misses}")
    print(f"  Mean   : {mean:>7.1f} ms")
    print(f"  p50    : {p50:>7.1f} ms  {'✅' if p50 < 60 else '❌'} (target <60ms)")
    print(f"  p95    : {p95:>7.1f} ms  {'✅' if p95 < 100 else '❌'} (target <100ms)")
    print(f"  p99    : {p99:>7.1f} ms  {'✅' if p99 < 150 else '❌'} (target <150ms)")
    print(f"  Max    : {mx:>7.1f} ms")
    print(f"\n  Overall: {'✅ PASS' if p95 < 100 else '❌ FAIL — check GPU load / Redis lag'}")
    print(f"{'='*60}\n")

    await redis.aclose()
    shm.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="E2E Latency Validation")
    parser.add_argument("--camera", default="cam01", help="Camera ID to test (default: cam01)")
    parser.add_argument("--frames", type=int, default=200, help="Frames to measure (after warmup)")
    parser.add_argument("--warmup", type=int, default=20, help="Warmup frames (excluded from stats)")
    parser.add_argument("--fps", type=float, default=25.0, help="Injection FPS (default: 25)")
    args = parser.parse_args()

    asyncio.run(run_latency_test(args.camera, args.frames, args.warmup, args.fps))


if __name__ == "__main__":
    main()
