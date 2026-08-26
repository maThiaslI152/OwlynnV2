#!/bin/bash
# Owlynn Launcher — browser-only, no Tauri (paused)
# Launches: containers → LM Studio (wait for user) → backend + frontend
# Lima Kali VM is auto-started by the frontend when Pentest mode is activated.
set -o pipefail
cd "$(dirname "$0")"

# Write project root for packaged Electron app
mkdir -p "${HOME}/.owlynn"
cat > "${HOME}/.owlynn/config.json" << EOF
{"project_root": "$(pwd)", "written_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
EOF

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
trap _cleanup INT TERM

echo ""
echo "══════════════════════════════"
echo "  Owlynn  —  Local Cowork Agent"
echo "══════════════════════════════"
echo ""

# ═══════════════════════════════════════════════════════════════════
# [1/3] MVP containers — Postgres (pgvector) + StirlingPDF
# ═══════════════════════════════════════════════════════════════════
_MVP_COMPOSE="docker-compose.mvp.yml"
# Lite default: Postgres only. StirlingPDF starts on-demand when PDF intake needs it.
_CORE_SERVICES="postgres"
echo "[1/3] PostgreSQL (StirlingPDF on-demand)..."

podman machine start 2>/dev/null || true
podman compose -f "$_MVP_COMPOSE" up -d $_CORE_SERVICES 2>/dev/null || \
podman-compose -f "$_MVP_COMPOSE" up -d $_CORE_SERVICES 2>/dev/null || \
docker compose -f "$_MVP_COMPOSE" up -d $_CORE_SERVICES 2>/dev/null || {
    echo "      WARNING: Could not start containers. Is Podman/Docker installed?"
}

echo "      Ready."

# ═══════════════════════════════════════════════════════════════════
# [2/3] Local LLM Engine (llama-server with MTP Speculative Decoding)
# ═══════════════════════════════════════════════════════════════════
echo "[2/3] Local LLM Engine (Port 1234)..."
if curl -sf http://127.0.0.1:1234/v1/models >/dev/null 2>&1; then
    echo "      LLM Server already active on port 1234."
else
    mkdir -p "${HOME}/.owlynn/logs"
    if [ -f "./scripts/run_llama_server.sh" ]; then
        echo "      Starting in-project llama-server with MTP draft speculative decoding (~180 tok/s)..."
        ./scripts/run_llama_server.sh > "${HOME}/.owlynn/logs/llama_server.log" 2>&1 &
        _LLAMA_PID=$!
        _PIDS+=("$_LLAMA_PID")
        
        echo "      Waiting for llama-server to load models..."
        _READY=0
        for i in $(seq 1 60); do
            if curl -sf http://127.0.0.1:1234/v1/models >/dev/null 2>&1; then
                _READY=1
                echo "      llama-server ready (PID $_LLAMA_PID). Log: ~/.owlynn/logs/llama_server.log"
                break
            fi
            if ! kill -0 "$_LLAMA_PID" 2>/dev/null; then
                echo "      ERROR: llama-server process exited unexpectedly."
                cat "${HOME}/.owlynn/logs/llama_server.log" | tail -n 20
                exit 1
            fi
            sleep 1
        done
        if [ "$_READY" -eq 0 ]; then
            echo "      ERROR: Timed out waiting for llama-server to initialize."
            cat "${HOME}/.owlynn/logs/llama_server.log" | tail -n 20
            exit 1
        fi
    else
        echo "      Not responding on port 1234. Please start LM Studio or llama-server."
        read -r -p "      Press Enter when ready... "
        curl -sf http://127.0.0.1:1234/v1/models >/dev/null 2>&1 || {
            echo "      Still not available. Exiting."
            exit 1
        }
    fi
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
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://owlynn:owlynn_password@127.0.0.1:5432/owlynn}"

if ! command -v uv &>/dev/null; then
    echo "      ERROR: uv is not installed. Please install uv first."
    exit 1
fi

# Database migrations (matches Electron runMigrations in main.ts)
echo "      Running database migrations..."
if ! uv run python -m alembic upgrade head; then
    echo "      WARNING: Database migration failed. Backend may start with degraded memory."
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
_BACKEND_PID=$!
_PIDS+=("$_BACKEND_PID")
echo "      Waiting for backend & LLMs to warm up (this may take up to 3 minutes)..."
for i in $(seq 1 180); do
    if curl -sf http://127.0.0.1:8000/api/health 2>/dev/null | grep -q ready; then
        echo "      Backend & LLMs ready (PID $_BACKEND_PID)."
        break
    fi
    sleep 1
done

# Start frontend (Electron App)
if [ -d "frontend-v2" ]; then
    (cd frontend-v2 && npm run dev >/dev/null 2>&1) &
    _PIDS+=("$!")
    echo "      Electron app launching (PID $!)."

    # Launch Brave Browser with Owlynn Extension loaded
    _BRAVE_CANDIDATES=(
        "/Volumes/KNV3_1TB/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        "${HOME}/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    )

    _BRAVE_BIN=""
    for _b in "${_BRAVE_CANDIDATES[@]}"; do
        if [ -f "$_b" ]; then
            _BRAVE_BIN="$_b"
            break
        fi
    done

    _EXT_DIR="$(pwd)/browser-extension"
    if [ -n "$_BRAVE_BIN" ] && [ -d "$_EXT_DIR" ]; then
        echo "      Launching Brave Browser with Owlynn extension..."
        "$_BRAVE_BIN" --load-extension="$_EXT_DIR" >/dev/null 2>&1 &
        _PIDS+=("$!")
    elif command -v open &>/dev/null && [ -d "/Applications/Brave Browser.app" ]; then
        echo "      Launching Brave Browser..."
        open -a "Brave Browser" 2>/dev/null || true
    fi

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

while kill -0 "$_BACKEND_PID" 2>/dev/null; do
    sleep 2
done
