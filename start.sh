#!/bin/bash
# Owlynn Launcher — browser-only, no Tauri (paused)
# Launches: containers → LM Studio (wait for user) → backend + frontend
set -o pipefail
cd "$(dirname "$0")"
# Parse arguments
DEBUG_MODE=0
for arg in "$@"; do
    if [ "$arg" == "--debug" ] || [ "$arg" == "-d" ]; then
        DEBUG_MODE=1
        export OWLYNN_DEBUG=1
        export OWLYNN_AUDIT_LOG_ENABLED=1
    fi
done
# Track background PIDs for Ctrl+C cleanup
_PIDS=()
_cleanup() {
    echo ""
    echo "── Stopping Owlynn ──"
    for pid in "${_PIDS[@]}"; do
        kill "$pid" 2>/dev/null
        wait "$pid" 2>/dev/null
    done
    echo "Done."
}
trap _cleanup EXIT

echo ""
echo "══════════════════════════════"
echo "  Owlynn  —  Local Cowork Agent"
echo "══════════════════════════════"
echo ""

# ═══════════════════════════════════════════════════════════════════
# [1/3] Podman containers — Qdrant + Redis (+ optional SearXNG)
# ═══════════════════════════════════════════════════════════════════
echo "[1/3] Containers..."
if podman ps --format '{{.Names}}' 2>/dev/null | grep -q 'owlynn_qdrant\|owlynn_redis'; then
    echo "      Already running."
else
    echo "      Starting (podman compose up)..."
    podman machine start 2>/dev/null || true
    podman compose up -d 2>/dev/null || podman-compose up -d 2>/dev/null || docker compose up -d 2>/dev/null || {
        echo "      ERROR: Could not start containers. Is Podman/Docker installed?"
        exit 1
    }
    sleep 5
fi
echo "      Ready."

# ═══════════════════════════════════════════════════════════════════
# [2/3] LM Studio — wait for user to launch it
# ═══════════════════════════════════════════════════════════════════
echo "[2/3] LM Studio..."
if curl -sf http://127.0.0.1:1234/v1/models >/dev/null 2>&1; then
    echo "      Ready."
else
    echo "      Not responding on port 1234."
    echo "      Please open LM Studio and start the server."
    read -r -p "      Press Enter when ready... "
    curl -sf http://127.0.0.1:1234/v1/models >/dev/null 2>&1 || {
        echo "      Still not available. Exiting."
        exit 1
    }
fi

# ═══════════════════════════════════════════════════════════════════
# [3/3] Backend + Frontend
# ═══════════════════════════════════════════════════════════════════
echo "[3/3] Backend + Frontend..."

# Load .env if present
if [ -f .env ]; then
    set -a; source .env; set +a
fi
# Local secrets override (e.g. DEEPSEEK_API_KEY) — see .env.local.example
if [ -f .env.local ]; then
    set -a; source .env.local; set +a
fi

# Docling model path (default to project-local cache)
export DOCLING_ARTIFACTS_PATH="${DOCLING_ARTIFACTS_PATH:-$(pwd)/.models/docling/}"
export PYTHONPATH="$(pwd):$PYTHONPATH"
export SEARXNG_URL="${SEARXNG_URL:-http://localhost:8888}"

source .venv/bin/activate 2>/dev/null || {
    echo "      ERROR: .venv not found. Run ./setup.sh first."
    exit 1
}

# Kill stale ports
lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null
lsof -ti:5173 2>/dev/null | xargs kill -9 2>/dev/null
sleep 1

# Start backend
if [ "$DEBUG_MODE" == "1" ]; then
    .venv/bin/python -m uvicorn src.api.server:app \
        --host 127.0.0.1 --port 8000 &
else
    .venv/bin/python -m uvicorn src.api.server:app \
        --host 127.0.0.1 --port 8000 \
        --no-access-log &
fi
_PIDS+=("$!")
echo "      Waiting for backend & LLMs to warm up (this may take up to 3 minutes)..."
for i in $(seq 1 180); do
    if curl -sf http://127.0.0.1:8000/api/health 2>/dev/null | grep -q ready; then
        echo "      Backend & LLMs ready (PID $!)."
        break
    fi
    sleep 1
done

# Start frontend (Vite dev server)
if [ -d "frontend-v2" ]; then
    (cd frontend-v2 && npx vite --host 127.0.0.1 --port 5173 >/dev/null 2>&1) &
    _PIDS+=("$!")
    for _ in $(seq 1 30); do
        curl -sf -o /dev/null http://127.0.0.1:5173 && break
        sleep 1
    done
    echo "      Frontend ready (PID $!)."
    echo ""
    echo "── Owlynn running ──"
    echo "   Browser: http://127.0.0.1:5173"
    echo "   API:     http://127.0.0.1:8000"
    echo "   Press Ctrl+C to stop."
    echo ""
    if [ -d "/Applications/Brave Browser.app" ]; then
        echo "      Opening Brave Browser with search extension loaded..."
        open -a "Brave Browser" "http://127.0.0.1:5173" --args --load-extension="$(pwd)/browser-extension" 2>/dev/null || open http://127.0.0.1:5173 2>/dev/null || true
    else
        open http://127.0.0.1:5173 2>/dev/null || true
    fi
else
    echo "      Frontend not found. API at http://127.0.0.1:8000"
    echo "      Press Ctrl+C to stop."
    echo ""
fi

wait
