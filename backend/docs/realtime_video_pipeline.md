# MediaMTX + PyAV Real-Time Video Pipeline

## Overview

This document describes a production-grade real-time video pipeline designed for 10 to 100 RTSP cameras with two clear goals:

- keep the viewer path under roughly 500 ms by using WebRTC for the frontend path
- keep the AI path frame-based and sampled, not full-rate and not coupled to playback

The implemented topology is:

```text
Camera (RTSP)
  -> MediaMTX
      -> WebRTC / WHEP for frontend
      -> Low-Latency HLS fallback
      -> RTSP pull from MediaMTX to PyAV workers
          -> sampled frames
          -> in-memory queue
          -> optional Kafka metadata publisher
```

## Why MediaMTX Is the Ingest Layer

MediaMTX describes itself as a "real-time media server and media proxy" and a "media router" that publishes, reads, proxies, records and plays back streams. It also documents that streams are automatically converted from one protocol to another and that the same stream can be read with WebRTC, RTSP, RTMP, and HLS.

That makes it the correct fanout layer for this system because:

- the camera is connected once, and readers do not multiply camera load
- WebRTC distribution is handled by MediaMTX instead of custom Python signaling logic
- HLS fallback is provided by the same ingest layer
- protocol conversion and buffering stay in the media server, not inside application workers

Official references:

- MediaMTX README: "media router", protocol conversion, multi-path support
- MediaMTX read overview: WebRTC, RTSP and HLS read support

## Why FFmpeg Is Not the Core Pipeline

FFmpeg subprocesses are useful for format conversion, but they are not the right core control plane for a 50+ camera extraction service:

- one subprocess per camera increases process count, memory footprint, restart complexity, and observability overhead
- subprocess supervision becomes the bottleneck instead of media routing
- the backend would own ingest, distribution, and extraction at the same time

In this design, FFmpeg is not the streaming backbone. MediaMTX is the streaming backbone. Python only consumes already-routed streams from MediaMTX for frame extraction.

## Why PyAV Replaces FFmpeg Workers

PyAV exposes FFmpeg libraries directly in Python. Its official container API supports:

- opening inputs through `av.open(...)`
- `container.demux(...)`
- `container.decode(...)`

That makes it appropriate for sampled frame extraction because:

- workers stay inside one Python process with asyncio orchestration
- frames are decoded in-process and can be queued without shelling out
- backpressure and sampling can be applied before the future AI stage
- reconnect logic stays in Python and is easier to observe and test

Official references:

- PyAV container docs for `av.open`, `demux`, and `decode`
- PyAV codec docs for codec context controls such as threading and frame skipping

## Latency Design

The latency-sensitive viewer path is:

```text
Camera -> MediaMTX -> WebRTC -> browser
```

This is the only path that should target sub-500 ms end-to-end latency.

Why it can stay low-latency:

- MediaMTX serves WebRTC directly
- `webrtcLocalUDPAddress` is enabled in the config so clients can use UDP instead of TCP
- HLS is present only as a fallback and is tuned for Low-Latency HLS, not as the primary path
- frame extraction workers never sit in the playback path

The AI-ready path is intentionally decoupled:

```text
Camera -> MediaMTX -> RTSP pull -> PyAV -> sampled queue
```

It can tolerate slightly higher latency as long as it remains stable and sampled.

## Scaling Model

The scaling target is 50+ cameras by separating concerns:

- MediaMTX handles camera ingest and frontend fanout
- one Python worker process hosts many asyncio-managed stream tasks
- each stream task decodes only one sampled RTSP pull from MediaMTX
- frame queues are bounded to prevent RAM growth
- frame rates are sampled to a low fixed rate such as 5 FPS

This avoids:

- one FFmpeg process per camera
- one camera connection per downstream consumer
- coupling frontend load to AI extraction load

## MediaMTX Configuration Notes

The provided [mediamtx.yml](/home/karthik/Downloads/pipeline_opencv/backend/mediamtx.yml) enables:

- RTSP ingest over TCP only
- WebRTC output
- low-latency HLS fallback
- on-demand source pulling
- absolute timestamp routing
- metrics and control API

Important settings and why they matter:

- `rtspTransports: [tcp]`
  This prioritizes stability through NATs and lossy networks.

- `sourceOnDemand: true`
  MediaMTX docs say URL sources can be pulled only when a reader is connected. This saves camera and network load.

- `useAbsoluteTimestamp: true`
  MediaMTX can preserve source timestamps instead of replacing them with current time. This helps downstream decode consistency.

- `hlsVariant: lowLatency`
  This keeps the fallback path responsive while remaining separate from the WebRTC primary path.

- `webrtcLocalUDPAddress: :8189`
  This enables UDP-based WebRTC, which is required for the low-latency target.

## Python Project Structure

The new implementation is isolated under:

```text
src/services/realtime_video/
  contracts.py
  frame_worker.py
  kafka_bridge.py
  mediamtx.py
  queue.py
  stream_manager.py
```

Responsibilities:

- `mediamtx.py`
  Builds RTSP, HLS and WHEP endpoints for a logical stream.

- `queue.py`
  Provides a bounded in-memory queue with deterministic drop behavior.

- `frame_worker.py`
  Runs one PyAV decode loop per logical stream and samples frames.

- `stream_manager.py`
  Starts and stops multiple workers inside one asyncio process.

- `kafka_bridge.py`
  Publishes frame metadata only, never raw frames.

## Frame Sampling Strategy

The worker uses a fixed-rate sampling gate. Sampled FPS is configured per stream and defaults to 5 FPS.

This is important because:

- decoding every frame for downstream AI is expensive and usually unnecessary
- sampling keeps CPU predictable across 10 to 100 streams
- downstream stages can still batch later because each sample carries stream and sequence metadata

## Backpressure Strategy

The queue is bounded and supports three policies:

- `drop_oldest`
- `drop_newest`
- `block`

The default is `drop_oldest`, which is the safest choice for near-real-time downstream consumers because it preserves the most recent frame instead of stale backlog.

## Failure Handling

The worker path is built around recovery instead of one-shot success:

- stream open failures trigger exponential backoff
- MediaMTX restarts appear to the worker as RTSP reconnect failures and are retried
- camera disconnects are retried through the same reconnect path
- bounded queues prevent RAM blow-ups during downstream stalls

## Performance Notes

### CPU vs GPU Decode

The current implementation is CPU decode oriented because PyAV works reliably without external GPU orchestration.

For higher densities:

- start with CPU decode and low sample FPS
- move only the extraction tier to hardware decode if profiling shows decode saturation
- keep MediaMTX unchanged as the ingest/distribution layer

### Batching Readiness

The queue payloads carry:

- camera id
- stream name
- frame sequence
- frame timestamp
- width / height / pixel format

That is enough to introduce future batch consumers without changing ingest or playback.

### Avoiding Per-Camera Processes

The implemented manager runs multiple workers in one asyncio process. That reduces:

- process count
- per-process RSS
- supervisor complexity
- restart storms during broker or network events

## Operational Guidance

Recommended viewer path:

- frontend consumes WebRTC through the WHEP URL returned by MediaMTX
- fallback player uses the HLS URL

Recommended extraction path:

- Python workers pull RTSP from MediaMTX, not from cameras directly

Recommended topic usage:

- publish only frame metadata to Kafka
- do not publish image payloads or encoded video to Kafka

## Official Sources

- MediaMTX README:
  https://raw.githubusercontent.com/bluenviron/mediamtx/main/README.md
- MediaMTX configuration reference:
  https://raw.githubusercontent.com/bluenviron/mediamtx/main/mediamtx.yml
- MediaMTX read overview:
  https://mediamtx.org/docs/read/overview
- PyAV containers API:
  https://pyav.org/docs/6.1.2/api/container.html
- PyAV codecs API:
  https://pyav.org/docs/6.1.2/api/codec.html
