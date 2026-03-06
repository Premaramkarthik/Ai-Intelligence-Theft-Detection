#!/bin/bash

# Antigravity Vision — Unified System Runner
# This script starts all Backend Services and the Modern Frontend directly.

# 0. Configuration
PROJECT_ROOT=$(pwd)
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
LOGS_DIR="$PROJECT_ROOT/logs"

mkdir -p "$LOGS_DIR"
rm -f "$LOGS_DIR"/*.log

# 1. Start required infrastructure (Redis, Postgres, MQTT)
echo "� Starting Docker infrastructure services..."
cd "$BACKEND_DIR"
docker compose up -d redis postgres mqtt
cd "$PROJECT_ROOT"

# 2. Cleanup stale processes and shared memory
echo "🛑 Performing system cleanup..."
pkill -f "services.signaling.main"
pkill -f "services.mediabridge.main"
pkill -f "services.inference.main"
pkill -f "services.alerting.main"
pkill -f "services.persistence.main"
pkill -f "npm run dev"

# Aggressive port cleanup
for port in 9001 8501 9101 9102 9103 9104; do
    pid=$(lsof -t -i :$port)
    if [ ! -z "$pid" ]; then
        echo "  -> Killing stale process on port $port (PID: $pid)"
        kill -9 $pid 2>/dev/null
    fi
done

# Clear stale Redis state and shared memory
echo "🧹 Clearing volatile state..."
docker exec backend-redis-1 redis-cli -a karthikS9 flushall >/dev/null 2>&1
rm -f /dev/shm/cam_*
rm -f /tmp/cam_*

# 3. Setup Backend Environment (VENV)
VENV_PATH="$BACKEND_DIR/.venv"
if [ ! -d "$VENV_PATH" ]; then
    VENV_PATH="$BACKEND_DIR/venv"
fi
VENV_BIN="$VENV_PATH/bin"

if [ ! -d "$VENV_BIN" ]; then
    echo "❌ Error: Backend virtual environment not found at backend/.venv or backend/venv"
    exit 1
fi

# 4. Start Backend Services
echo "🚀 Launching Antigravity Vision Services..."
cd "$BACKEND_DIR"
export PYTHONPATH="$BACKEND_DIR"

echo "  -> Signaling (API)..."
"$VENV_BIN/uvicorn" services.signaling.main:app --host 0.0.0.0 --port 9001 > "$LOGS_DIR/backend_signaling.log" 2>&1 &
SIG_PID=$!

echo "  -> MediaBridge (Capture)..."
"$VENV_BIN/python3" -m services.mediabridge.main > "$LOGS_DIR/backend_mediabridge.log" 2>&1 &
MB_PID=$!

echo "  -> Inference (AI)..."
"$VENV_BIN/python3" -m services.inference.main > "$LOGS_DIR/backend_inference.log" 2>&1 &
INF_PID=$!

echo "  -> Alerting..."
"$VENV_BIN/python3" -m services.alerting.main > "$LOGS_DIR/backend_alerting.log" 2>&1 &
ALT_PID=$!

echo "  -> Persistence..."
"$VENV_BIN/python3" -m services.persistence.main > "$LOGS_DIR/backend_persistence.log" 2>&1 &
PER_PID=$!

cd "$PROJECT_ROOT"

# 5. Start Modern Frontend
echo "  -> Modern Dashboard (React)..."
cd "$FRONTEND_DIR"
npm run dev > "$LOGS_DIR/frontend.log" 2>&1 &
FRONT_PID=$!
cd "$PROJECT_ROOT"

echo "----------------------------------------------------"
echo "✅ Antigravity Vision System is LIVE!"
echo "🌐 Modern Dashboard: http://localhost:8080/"
echo "🌐 API Documentation: http://localhost:9001/docs"
echo "----------------------------------------------------"
echo "💡 All logs are in the '$LOGS_DIR/' folder."
echo "🛑 Press Ctrl+C to stop all services"

# 6. Lifecycle Management
trap "echo '🛑 Stopping system...'; kill $SIG_PID $MB_PID $INF_PID $ALT_PID $PER_PID $FRONT_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
