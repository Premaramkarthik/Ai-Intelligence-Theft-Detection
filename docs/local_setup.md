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

- **MediaBridge**: `python3 services/mediabridge/main.py`
- **Inference**: `python3 services/inference/main.py`
- **Signaling**: `python3 services/signaling/main.py`
- **Alerting**: `python3 services/alerting/main.py`
- **Persistence**: `python3 services/persistence/main.py`

---

## 💡 Troubleshooting

### Shared Memory Leaks
If you experience "FileExistsError" or "Leaked shared_memory objects", use the cleanup command:
```bash
./scripts/run_local.sh --cleanup
```

### ModuleNotFoundError
Ensure you are running commands from the **root directory** of the project and that your `PYTHONPATH` includes the current directory:
```bash
export PYTHONPATH=$PYTHONPATH:.
```

### RTSP/Webcam Failures
If the `mediabridge` logs show connection failures:
1. Verify the URL in `.env`.
2. For local webcams, ensure no other application (like Zoom) is using the camera.
3. Test connectivity with `ffplay <url>`.
