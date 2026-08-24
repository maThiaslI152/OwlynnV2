#!/bin/bash
# Owlynn Setup — one-time bootstrap for a fresh checkout
# Prerequisites: Podman/Docker, Python 3.12+, Node 18+
set -e

echo ""
echo "══════════════════════════════"
echo "  Owlynn Setup"
echo "══════════════════════════════"
echo ""

# ═══════════════════════════════════════════════════════════════════
# [1/4] Start MVP containers — Postgres (pgvector) + StirlingPDF
# ═══════════════════════════════════════════════════════════════════
_MVP_COMPOSE="docker-compose.mvp.yml"
_CORE_SERVICES="postgres stirling-pdf"
echo "[1/4] Starting containers..."
podman machine start 2>/dev/null || true
podman compose -f "$_MVP_COMPOSE" up -d $_CORE_SERVICES 2>/dev/null || \
podman-compose -f "$_MVP_COMPOSE" up -d $_CORE_SERVICES 2>/dev/null || \
docker compose -f "$_MVP_COMPOSE" up -d $_CORE_SERVICES 2>/dev/null || {
    echo "      ERROR: Could not start containers. Is Podman/Docker installed?"
    exit 1
}
sleep 3
echo "      Ready."

# ═══════════════════════════════════════════════════════════════════
# [2/4] Create virtual environment + install dependencies
# ═══════════════════════════════════════════════════════════════════
echo "[2/4] Python environment..."
rm -rf .venv

echo "      Using uv"
uv venv
uv sync
echo "      Dependencies installed."

# ═══════════════════════════════════════════════════════════════════
# [3/4] Download Docling document models (~2 GB, one-time)
# ═══════════════════════════════════════════════════════════════════
echo "[3/4] Docling models..."
MODEL_DIR="$(pwd)/.models/docling"
mkdir -p "$MODEL_DIR"

if [ -f "$MODEL_DIR/ds4sd--docling-models/config.json" ]; then
    echo "      Already downloaded (skip with: rm -rf .models/docling)."
else
    echo "      Downloading document processing models (~2 GB)..."
    echo "      This is a one-time download. Models are stored in .models/docling/"
    echo ""
    uv run python -c "
from docling.utils.model_downloader import download_models
from pathlib import Path
download_models(output_dir=Path('$MODEL_DIR'))
" 2>&1 | tail -3
    echo ""
    echo "      Models downloaded to .models/docling/"
fi

# ═══════════════════════════════════════════════════════════════════
# [4/5] Vendor offline Chart.js (workspace HTML charts)
# ═══════════════════════════════════════════════════════════════════
echo "[4/5] Chart.js vendor bundle..."
bash scripts/vendor_chartjs.sh

# ═══════════════════════════════════════════════════════════════════
# [5/5] Copy .env.example → .env if missing
# ═══════════════════════════════════════════════════════════════════
echo "[5/5] Configuration..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "      Created .env from .env.example — edit as needed."
else
    echo "      .env already exists."
fi

echo ""
echo "═══ Setup complete ═══"
echo ""
echo "   Next steps:"
echo "   1. Edit .env and set MEDIUM_LLM_MODEL_NAME to your LM Studio model"
echo "   2. Start LM Studio with your models loaded"
echo "   3. Run ./start.sh to launch Owlynn"
echo ""
