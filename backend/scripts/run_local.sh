#!/bin/bash

# Pipeline OpenCV — Local Services Runner
# This script starts all backend services in the background using your local Python environment.

# 0. Start required infrastructure (Redis, Postgres, MQTT)
echo "🐳 Starting Docker infrastructure services..."
docker compose up -d redis postgres mqtt

# 0. Cleanup any stale processes from previous runs
./scripts/cleanup.sh

# 1. Setup paths
VENV_PATH="./.venv"
if [ ! -d "$VENV_PATH" ]; then
    VENV_PATH="./venv"
fi
VENV_BIN="$VENV_PATH/bin"

if [ ! -d "$VENV_BIN" ]; then
    echo "❌ Error: Virtual environment not found at .venv or venv"
    exit 1
fi

echo "🚀 Starting Pipeline OpenCV Services locally (using $VENV_PATH)..."

# 2. Preparation
mkdir -p logs
rm -f logs/*.log

# 3. Start Services
echo "  -> Signaling (API)..."
$VENV_BIN/uvicorn services.signaling.main:app --host 0.0.0.0 --port 9001 > logs/signaling.log 2>&1 &
SIG_PID=$!

echo "  -> MediaBridge (Capture)..."
$VENV_BIN/python3 -m services.mediabridge.main > logs/mediabridge.log 2>&1 &
MB_PID=$!

echo "  -> Inference (AI)..."
$VENV_BIN/python3 -m services.inference.main > logs/inference.log 2>&1 &
INF_PID=$!

echo "  -> Alerting..."
$VENV_BIN/python3 -m services.alerting.main > logs/alerting.log 2>&1 &
ALT_PID=$!

echo "  -> Persistence..."
$VENV_BIN/python3 -m services.persistence.main > logs/persistence.log 2>&1 &
PER_PID=$!

echo "  -> Streamlit Dashboard..."
export STREAMLIT_SERVER_HEADLESS=true
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
$VENV_BIN/streamlit run app.py --server.port 8501 > logs/streamlit.log 2>&1 &
STR_PID=$!

echo "✅ All services started!"
echo "🔍 Check logs/ folder for output."
echo "🌐 Dashboard ready at http://localhost:8501"

# Handle shutdown
trap "kill $SIG_PID $MB_PID $INF_PID $ALT_PID $PER_PID $STR_PID 2>/dev/null; echo '🛑 Services stopped.'; exit" SIGINT SIGTERM
wait
