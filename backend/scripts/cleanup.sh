#!/bin/bash
# Pipeline OpenCV — Cleanup Utility
# Kills stale services and clears shared memory segments.

echo "🛑 Cleaning up Pipeline OpenCV services..."

# 1. Kill Python processes running our services
pkill -f "services.signaling.main"
pkill -f "services.mediabridge.main"
pkill -f "services.inference.main"
pkill -f "services.alerting.main"
pkill -f "services.persistence.main"
pkill -f "streamlit run app.py"

# 2. Kill processes by port (Backup)
for port in 9001 8501 9101 9102 9103 9104; do
    pid=$(lsof -t -i :$port)
    if [ ! -z "$pid" ]; then
        echo "  -> Killing process on port $port (PID: $pid)"
        kill -9 $pid 2>/dev/null
    fi
done

# 3. Clear Shared Memory
echo "  -> Clearing shared memory segments..."
rm -f /dev/shm/cam_*_ring
rm -f /dev/shm/cam_*_idx

echo "✅ Cleanup complete. You can now run ./scripts/run_local.sh"
