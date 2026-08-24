#!/usr/bin/env bash
# Build the self-contained backend payload for Electron extraResources (owlynn-backend).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_DIR="${ROOT}/dist/backend-bundle"
PKG_JSON="${ROOT}/frontend-v2/package.json"

if [[ ! -f "${PKG_JSON}" ]]; then
  echo "ERROR: frontend-v2/package.json not found"
  exit 1
fi

VERSION="$(node -p "require('${PKG_JSON}').version" 2>/dev/null || sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${PKG_JSON}" | head -1)"

echo ""
echo "════════════════════════════════════════"
echo "  Owlynn backend bundle (v${VERSION})"
echo "════════════════════════════════════════"
echo ""

cd "${ROOT}"

if [[ ! -f "${ROOT}/frontend-v2/dist/index.html" ]]; then
  echo "ERROR: frontend-v2/dist/index.html missing. Run: cd frontend-v2 && tsc -b && vite build"
  exit 1
fi

echo "[1/3] Syncing Python environment (uv sync → arm64 .venv)..."
if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
uv sync

echo "[2/3] Vendoring Chart.js..."
bash scripts/vendor_chartjs.sh

echo "[3/3] Copying payload to dist/backend-bundle/..."
rm -rf "${BUNDLE_DIR}"
mkdir -p "${BUNDLE_DIR}"

copy_tree() {
  local rel="$1"
  local src="${ROOT}/${rel}"
  if [[ ! -e "${src}" ]]; then
    echo "  WARN: missing ${rel}"
    return
  fi
  local dest="${BUNDLE_DIR}/${rel}"
  mkdir -p "$(dirname "${dest}")"
  cp -R "${src}" "${dest}"
  echo "  + ${rel}"
}

for item in \
  src \
  alembic \
  alembic.ini \
  assets/vendor \
  skills \
  mcp_config.json \
  pyproject.toml \
  uv.lock \
  docker-compose.mvp.yml \
  frontend-v2/dist \
  .venv
do
  copy_tree "${item}"
done

echo "${VERSION}" > "${BUNDLE_DIR}/VERSION"

SIZE="$(du -sh "${BUNDLE_DIR}" | cut -f1)"
echo ""
echo "Backend bundle ready: dist/backend-bundle/ (${SIZE})"
echo ""
