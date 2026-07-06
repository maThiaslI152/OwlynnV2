#!/bin/bash
# Owlynn Launcher — browser-only, no Tauri (paused)
# Launches: containers → LM Studio (wait for user) → backend + frontend
# Lima Kali VM is auto-started by the frontend when Pentest mode is activated.
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
    # Stop Lima Kali VM if running (saves ~2GB RAM)
    if command -v limactl &>/dev/null && limactl list 2>/dev/null | grep -q "owlynn-kali.*Running"; then
        echo "      Stopping Kali VM..."
        limactl stop owlynn-kali 2>/dev/null || true
    fi
    echo "Done."
}
trap _cleanup EXIT

echo ""
echo "══════════════════════════════"
echo "  Owlynn  —  Local Cowork Agent"
echo "══════════════════════════════"
echo ""

# ═══════════════════════════════════════════════════════════════════
# [1/3] Qdrant + Redis (containers preferred, binary fallback)
# ═══════════════════════════════════════════════════════════════════
echo "[1/3] Qdrant + Redis..."

_qdrant_started_local=0

# Try containers first
if podman machine start 2>/dev/null || true; then
    podman compose up -d qdrant redis 2>/dev/null || \
    podman-compose up -d qdrant redis 2>/dev/null || \
    docker compose up -d qdrant redis 2>/dev/null || true
fi

# Check if Qdrant is already up (either from containers or previous native run)
if curl -sf http://127.0.0.1:6333/healthz >/dev/null 2>&1; then
    echo "      Qdrant ready."
else
    # Try native Qdrant binary (installed via GitHub releases to ~/bin or /usr/local/bin)
    _QDRANT_BIN=""
    if command -v qdrant &>/dev/null; then
        _QDRANT_BIN="qdrant"
    elif [ -x "${HOME}/bin/qdrant" ]; then
        _QDRANT_BIN="${HOME}/bin/qdrant"
    fi
    if [ -n "$_QDRANT_BIN" ]; then
        echo "      Starting native Qdrant binary..."
        mkdir -p "${HOME}/.owlynn/storage"
        (cd "${HOME}/.owlynn" && "$_QDRANT_BIN" >/dev/null 2>&1) &
        _PIDS+=("$!")
        _qdrant_started_local=1
        # Wait up to 10s for Qdrant to be ready
        for _i in $(seq 1 10); do
            sleep 1
            if curl -sf http://127.0.0.1:6333/healthz >/dev/null 2>&1; then
                echo "      Qdrant ready (native binary)."
                break
            fi
        done
    else
        echo "      WARNING: Qdrant not available. Long-term memory (mem0) will be disabled."
        echo "      Install: curl -L https://github.com/qdrant/qdrant/releases/latest/download/qdrant-aarch64-apple-darwin.tar.gz | tar xz -C ~/bin"
    fi
fi

# Redis (best-effort — only needed for session cache)
if ! curl -sf http://127.0.0.1:6379 >/dev/null 2>&1; then
    if command -v redis-server &>/dev/null; then
        redis-server --daemonize yes --logfile /dev/null 2>/dev/null || true
    fi
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
# DeepSeek key written by the UI (fallback for terminal sessions where Keychain may be locked)
if [ -f "${HOME}/.owlynn/secrets.env" ]; then
    set -a; source "${HOME}/.owlynn/secrets.env"; set +a
    if [ -n "$DEEPSEEK_API_KEY" ]; then
        echo "      Loaded DeepSeek API key from ~/.owlynn/secrets.env"
    fi
fi

# Docling model path (default to project-local cache)
export DOCLING_ARTIFACTS_PATH="${DOCLING_ARTIFACTS_PATH:-$(pwd)/.models/docling/}"
export PYTHONPATH="$(pwd):$PYTHONPATH"
export STIRLING_PDF_URL="${STIRLING_PDF_URL:-http://localhost:8090}"
export STIRLING_PDF_API_KEY="${STIRLING_PDF_API_KEY:-owlynn-local-dev}"

if ! command -v uv &>/dev/null; then
    echo "      ERROR: uv is not installed. Please install uv first."
    exit 1
fi

# Kill stale ports
lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null
lsof -ti:5173 2>/dev/null | xargs kill -9 2>/dev/null
sleep 1

# Start backend
if [ "$DEBUG_MODE" == "1" ]; then
    uv run python -m uvicorn src.api.server:app \
        --host 127.0.0.1 --port 8000 \
        --ws-max-size 16777216 &
else
    uv run python -m uvicorn src.api.server:app \
        --host 127.0.0.1 --port 8000 \
        --ws-max-size 16777216 \
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

# Start frontend (Electron App)
if [ -d "frontend-v2" ]; then
    (cd frontend-v2 && npm run dev >/dev/null 2>&1) &
    _PIDS+=("$!")
    echo "      Electron app launching (PID $!)."
    echo ""
    echo "── Owlynn running ──"
    echo "   API:     http://127.0.0.1:8000"
    echo "   Press Ctrl+C to stop."
    # Show Lima Kali VM status (auto-started when Pentest mode is activated)
    if command -v limactl &>/dev/null; then
        _LIMA_STATUS=$(limactl list --format '{{.Name}} {{.Status}}' 2>/dev/null | grep "owlynn-kali" | awk '{print $2}')
        if [ -n "$_LIMA_STATUS" ]; then
            if [ "$_LIMA_STATUS" == "Running" ]; then
                echo "   Kali VM: running (SSH 127.0.0.1:60022)"
            else
                echo "   Kali VM: stopped (auto-starts on Pentest mode)"
            fi
        else
            echo "   Kali VM: not created (run ./scripts/setup-kali-lima.sh)"
        fi
    fi
    echo ""
else
    echo "      Frontend not found. API at http://127.0.0.1:8000"
    echo "      Press Ctrl+C to stop."
    echo ""
fi

wait
