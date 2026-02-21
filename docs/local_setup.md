# Local Setup Guide (Without Docker)

This guide explains how to set up and run the Pipeline OpenCV services directly on your host machine for development or debugging.

## Prerequisites

1.  **Python 3.11+**: Ensure you have Python installed.
2.  **External Dependencies**: Even when running the services locally, you still need Redis, PostgreSQL, and MQTT. We recommend running just the infrastructure (and pgAdmin) via Docker:
    ```bash
    docker compose up -d redis postgres mqtt pgadmin
    ```
    *Alternatively, install them natively on your OS and update `.env` accordingly.*

---

## 1. Virtual Environment & Dependencies

First, create a virtual environment to isolate your project dependencies:

```bash
# 1. Create the venv
python -m venv venv

# 2. Activate it
# On Linux/macOS:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# 3. Install core dependencies
pip install -r requirements.txt

# 4. Install the project in editable mode
# This allows 'libs' and 'services' to be imported correctly
pip install -e .
```

---

## 2. Configuration

Ensure your `.env` file is present in the root directory. Since you are running locally, `REDIS_HOST` and `POSTGRES_HOST` should likely be `localhost`.

```bash
# Update .env for local run
REDIS_HOST=localhost
POSTGRES_HOST=localhost

## 2.1 Using Laptop Webcam
To use your laptop's integrated webcam:
1.  Identify the index (usually `0`).
2.  Update `.env`: `CAMERA_SOURCES=0`.
3.  Check [Troubleshooting](#5-troubleshooting) if access is denied.
# Ensure paths like EVIDENCE_STORAGE_PATH exist on your machine
```

---

## 3. Running Services

Each service is a standalone Python application. You will need to open multiple terminals (or use a tool like `tmux` or `screen`) and run them individually.

### A. Signaling Service (API)
```bash
uvicorn services.signaling.main:app --host 0.0.0.0 --port 9000
```

### B. MediaBridge (Capture)
```bash
python -m services.mediabridge.main
```

### C. Inference (AI Engine)
```bash
python -m services.inference.main
```

### D. Alerting (Telegram/MQTT)
```bash
python -m services.alerting.main
```

### E. Persistence (DB Worker)
```bash
python -m services.persistence.main
```

---

## 4. Why this works?

- **Root Installation**: By running `pip install -e .`, the directory structure is registered with your Python environment. This means `import libs.shared` and `import services.signaling` will resolve correctly regardless of which directory you run the python commands from.
- **Shared Memory**: On Linux, shared memory (`/dev/shm`) works natively between local processes. If you are on Windows, ensure the `multiprocessing.shared_memory` implementation is compatible with your needs.

## 5. Troubleshooting
- **ImportErrors**: If you get "ModuleNotFoundError", ensure you ran `pip install -e .` inside your active venv.
- **Connection Refused**: Ensure your Redis and Postgres instances are running and that the credentials in `.env` match.
