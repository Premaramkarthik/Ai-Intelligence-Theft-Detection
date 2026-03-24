# RTSP Camera Backend

Production-oriented FastAPI backend for RTSP camera management with:

- frontend-friendly REST contracts
- HLS stream playback URLs for browser clients
- per-camera worker processes
- Kafka metadata events and WebSocket fan-out
- PostgreSQL persistence through `asyncpg`
- SQL scripts and migrations stored separately
- one-query-per-file SQL organization for clear repository contracts

## Architecture

Control plane:

`Frontend -> FastAPI REST/WebSocket -> PostgreSQL + Kafka`

Media plane:

`RTSP Camera -> Worker Process -> FFmpeg -> HLS playlist/segments -> Frontend player`

Event plane:

`Worker -> Kafka topics -> FastAPI consumer -> WebSocket updates`

The `deep_sort_realtime` folder is wired in through an optional tracker bridge so `camera.ai_results` events can carry Deep SORT tracking payloads when detections are available.

## Main Endpoints

- `POST /cameras`
- `GET /cameras`
- `GET /cameras/{camera_id}`
- `PUT /cameras/{camera_id}`
- `DELETE /cameras/{camera_id}`
- `POST /cameras/{camera_id}/validate`
- `POST /streams/{camera_id}/start`
- `POST /streams/{camera_id}/stop`
- `GET /streams/{camera_id}/status`
- `GET /streams/{camera_id}/info`
- `GET /health`
- `GET /health/db`
- `GET /health/stream/{camera_id}`
- `WS /streams/ws/updates`

## Environment

Typical settings:

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/rtsp_camera"
export KAFKA_BOOTSTRAP_SERVERS="localhost:9092"
export PUBLIC_API_BASE_URL="http://localhost:8000"
export CORS_ORIGINS="http://localhost:3000"
export FFMPEG_BINARY="ffmpeg"
export FFPROBE_BINARY="ffprobe"
```

Optional tracking bridge:

```bash
export ENABLE_TRACKER_BRIDGE=true
export TRACKER_EMBEDDER=clip_ViT-B/32
```

## SQL Layout

```text
scripts/sql/
├── camera/
│   ├── delete_camera.sql
│   ├── get_camera_by_id.sql
│   ├── insert_camera.sql
│   ├── list_cameras.sql
│   ├── update_camera.sql
│   └── update_camera_validation.sql
├── common/
│   └── health_check.sql
└── stream/
    ├── apply_stream_event.sql
    ├── get_stream.sql
    ├── insert_stream.sql
    ├── list_streams.sql
    └── update_stream_status.sql
```

Each repository method loads a single SQL file, which keeps query ownership explicit and easy to change safely.

## Run

1. Install dependencies:

```bash
cd /home/karthik/Downloads/pipeline_opencv/backend
python -m venv .venv
. .venv/bin/activate
python -m ensurepip --upgrade
python -m pip install -e ".[dev]"
```

2. Run migrations:

```bash
.venv/bin/python -m src.utils.migration_runner
```

3. Start the API:

```bash
.venv/bin/uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

4. Frontend integration:

- HLS playlist URL: `/media/hls/{camera_id}/index.m3u8`
- Realtime updates: `ws://localhost:8000/streams/ws/updates`
- Filtered realtime updates: `ws://localhost:8000/streams/ws/updates?camera_id=cam_123`

## Kafka Topics

- `camera.status`
- `camera.events`
- `camera.ai_results`

## Quality Checks

Run after dependencies are installed:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check src tests
.venv/bin/python -m pylint src tests
```
