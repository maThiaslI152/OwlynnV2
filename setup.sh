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
# [1/4] Start containers — Qdrant + Redis
# ═══════════════════════════════════════════════════════════════════
echo "[1/4] Starting containers..."
podman machine start 2>/dev/null || true
podman compose up -d 2>/dev/null || podman-compose up -d 2>/dev/null || docker compose up -d 2>/dev/null || {
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

if command -v python3.12 &>/dev/null; then
    PYTHON=python3.12
elif command -v python3.13 &>/dev/null; then
    PYTHON=python3.13
elif command -v python3.11 &>/dev/null; then
    PYTHON=python3.11
else
    PYTHON=python3
fi

echo "      Using $PYTHON"
$PYTHON -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt
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
    source .venv/bin/activate
    python3 -c "
from docling.utils.model_downloader import download_models
from pathlib import Path
download_models(output_dir=Path('$MODEL_DIR'))
" 2>&1 | tail -3
    echo ""
    echo "      Models downloaded to .models/docling/"
fi

# ═══════════════════════════════════════════════════════════════════
# [4/4] Copy .env.example → .env if missing
# ═══════════════════════════════════════════════════════════════════
echo "[4/4] Configuration..."
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
