# Local Setup Guide (Dev Mode)

This guide explains how to set up and run the Pipeline OpenCV services locally for development, debugging, and advanced testing.

---

## 🚀 The One-Click Way (Recommended)

We've provided a script that automates the entire local setup process, including infrastructure and service management:

```bash
chmod +x scripts/run_local.sh
./scripts/run_local.sh
```
This script will:
1. Start Redis, PostgreSQL, and MQTT via Docker.
2. Launch each backend service in the background.
3. Start the Streamlit Dashboard.

---

## 🛠️ Manual Step-by-Step Setup

### 1. Prerequisites
- **Python 3.11+**
- **Docker**: For running the database and message brokers.

### 2. Environment & Dependencies
```bash
# 1. Create and activate venv
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Setup .env
cp .env.example .env
```

### 3. Infrastructure Only
If you want to run the core services (MediaBridge, Inference) in your IDE but keep the database in Docker:
```bash
docker compose up redis postgres mqtt -d
```

### 4. Running Services Individually
To run services with hot-reloading or individual log control:

- **Signaling** (API Gateway): `python3 services/signaling/main.py`
- **MediaBridge** (Ingestion): `python3 services/mediabridge/main.py`
- **Inference** (AI Pipeline): `python3 services/inference/main.py`

---

## 📽️ Adding Cameras
In the current release, cameras are added **dynamically** via the API rather than static `.env` lists.

1.  Start the services.
2.  Open Swagger at `http://localhost:9000/docs`.
3.  Use the `POST /api/camera/connect` endpoint to launch a worker for your local webcam or RTSP stream.

---

## 💡 Troubleshooting

### Shared Memory Leaks
If you experience "FileExistsError" or "Leaked shared_memory objects", use the cleanup command:
```bash
./scripts/run_local.sh --cleanup
```

### ModuleNotFoundError
Ensure you are running commands from the **root directory** and that your `PYTHONPATH` includes `.`:
```bash
export PYTHONPATH=$PYTHONPATH:.
```

### Camera Failures
If the `mediabridge` logs show connection failures:
1. Verify the credentials in your API request.
2. For local webcams (`/dev/video0`), Ensure no other application is using the device.
3. Test RTSP connectivity directly with `ffplay <url>`.
