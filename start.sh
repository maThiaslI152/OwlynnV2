#!/bin/bash
# Owlynn Launcher — simple and reliable
# Launches: containers, LM Studio (waits for user), backend, frontend, desktop app
# The desktop app runs via a debug .app bundle so macOS TCC privacy system
# (microphone/speech recognition) reads Info.plist correctly.
set -o pipefail
cd "$(dirname "$0")"

# Track background PIDs for cleanup
_CLEANUP_PIDS=()

_cleanup() {
    echo ""
    echo "Stopping services..."
    for pid in "${_CLEANUP_PIDS[@]}"; do
        kill "$pid" 2>/dev/null
        wait "$pid" 2>/dev/null
    done
    echo "Done."
}
trap _cleanup EXIT

echo ""
echo "── Owlynn ──"
echo ""

# 1. Podman / Docker containers
echo "[1/4] Containers..."
# Run container check in background with hard 15s timeout to avoid hanging
(
    _running=false
    podman ps 2>/dev/null | grep -q owlynn_qdrant && podman ps 2>/dev/null | grep -q owlynn_redis && _running=true
    if $_running; then
        echo "      Already running."
    else
        echo "      Starting containers..."
        podman machine start 2>/dev/null
        podman compose up -d 2>/dev/null || podman-compose up -d 2>/dev/null || docker compose up -d 2>/dev/null
        echo "      Waiting 8s for services..."
        sleep 8
    fi
) &
_container_pid=$!
(sleep 15 && kill $_container_pid 2>/dev/null) &
_timer_pid=$!
wait $_container_pid 2>/dev/null
kill $_timer_pid 2>/dev/null
wait $_timer_pid 2>/dev/null
echo "      Done."

# Check Podman machine memory
_podman_mem=$(podman machine inspect 2>/dev/null | grep -o '"Memory":[0-9]*' | grep -o '[0-9]*' || echo "0")
if [ "$_podman_mem" -gt 0 ] && [ "$_podman_mem" -lt 2048 ]; then
    echo "      ⚠️  Podman machine memory is low ($_podman_mem MB). Recommend: podman machine set --memory 4096"
fi

# 2. LM Studio
echo "[2/4] LM Studio..."
if curl -s http://127.0.0.1:1234/v1/models >/dev/null 2>&1; then
    echo "      Ready."
else
    echo "      Not responding on port 1234."
    echo "      Please open LM Studio and start the server."
    read -p "      Press Enter when ready..."
    curl -s http://127.0.0.1:1234/v1/models >/dev/null 2>&1 || { echo "      Still not available. Exiting."; exit 1; }
fi

# 3. Backend
echo "[3/4] Backend..."
lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null
sleep 1

export PYTHONPATH="$(pwd):$PYTHONPATH"
export SEARXNG_URL=http://localhost:8888
source .venv/bin/activate 2>/dev/null

.venv/bin/python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --no-access-log &
PID=$!

for i in $(seq 1 30); do
    curl -s http://127.0.0.1:8000/api/health 2>/dev/null | grep -q ready && break
    sleep 1
done
echo "      Ready (PID $PID)."
_CLEANUP_PIDS+=("$PID")

# 4. Frontend v2 + Desktop app
echo "[4/4] Frontend + app..."
echo ""
echo "      Press Ctrl+C to stop."
echo ""

export PATH="$PATH:$HOME/.cargo/bin"

# Kill any stale Vite dev server on port 5173
lsof -ti:5173 2>/dev/null | xargs kill -9 2>/dev/null
sleep 1

# Start frontend-v2 dev server for Tauri devPath
if [ -d "frontend-v2" ]; then
    (cd frontend-v2 && npm run dev -- --host 127.0.0.1 >/dev/null 2>&1) &
    FRONTEND_PID=$!
    for i in $(seq 1 30); do
        curl -s -o /dev/null http://127.0.0.1:5173 && break
        sleep 1
    done
    echo "      Vite dev server ready (PID $FRONTEND_PID)."
    _CLEANUP_PIDS+=("$FRONTEND_PID")
fi

# Use the locally installed Tauri CLI instead of fetching via npx
_LOCAL_TAURI="./frontend-v2/node_modules/.bin/tauri"
if [ -x "$_LOCAL_TAURI" ]; then
    echo "      Launching Tauri desktop app..."

    # Build the Swift helper for SoundAnalysis + WhisperKit
    if [ -d "src-tauri/whisperkit-helper" ]; then
        echo "      Building whisperkit-helper..."
        (cd src-tauri/whisperkit-helper && swift build -c release >/dev/null 2>&1) &
        _HELPER_BUILD_PID=$!
        wait $_HELPER_BUILD_PID 2>/dev/null
        export WHISPERKIT_HELPER_PATH="$(pwd)/src-tauri/whisperkit-helper/.build/release/whisperkit-helper"
        echo "      Helper ready."
    fi

    # Build the frontend first for the .app bundle
    (cd frontend-v2 && npm run build >/dev/null 2>&1) &
    _BUILD_PID=$!
    wait $_BUILD_PID 2>/dev/null
    echo "      Frontend built."

    # Launch the debug .app bundle (has proper Info.plist for mic/speech)
    # Uses the built frontend from dist/, not Vite dev server HMR.
    # If you need HMR, rebuild with: npx tauri dev
    _APP_BUNDLE="src-tauri/target/debug/bundle/macos/Owlynn.app"
    if [ ! -d "$_APP_BUNDLE" ]; then
        echo "      Building debug .app bundle (first time)..."
        "$_LOCAL_TAURI" build --debug -v 2>&1 | tail -1
    fi

    if [ -d "$_APP_BUNDLE" ]; then
        echo "      Launching Owlynn.app..."
        open "$_APP_BUNDLE"
        echo "      App launched. Restart script to relaunch."
        wait
    else
        echo "      .app bundle not found, falling back to tauri dev..."
        "$_LOCAL_TAURI" dev
    fi
else
    echo "      Tauri not available. Open http://127.0.0.1:8000"
    wait $PID
fi
