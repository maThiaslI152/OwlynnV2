#!/bin/bash
# =============================================================================
# Setup llama.cpp inside Owlynn (Verified build b9553 for Gemma 4 MTP)
# =============================================================================
# Build commit: 9e3b928fd (b9553)
# Tested & verified: Gemma 4 MTP draft speculative decoding (~88 -> ~180 tok/s)
# Note: Newer builds (e.g. b9702/b9717) crash with 'invalid vector subscript'
#       due to an upstream regression in the gemma4-assistant loader path.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LLAMA_DIR="${ROOT_DIR}/llama.cpp"
TARGET_COMMIT="9e3b928fd"

echo "══════════════════════════════════════════════════════════════"
echo "  Owlynn — llama.cpp (b9553 / commit ${TARGET_COMMIT}) Setup"
echo "══════════════════════════════════════════════════════════════"

# 1. Clone repository if not present
if [ ! -d "${LLAMA_DIR}" ]; then
    echo "── [1/3] Cloning llama.cpp repository into ${LLAMA_DIR}..."
    git clone https://github.com/ggerganov/llama.cpp.git "${LLAMA_DIR}"
else
    echo "── [1/3] llama.cpp repository already present at ${LLAMA_DIR}"
fi

# 2. Checkout verified commit
cd "${LLAMA_DIR}"
echo "── [2/3] Checking out verified working commit ${TARGET_COMMIT}..."
git fetch origin "${TARGET_COMMIT}" --depth=1 2>/dev/null || git fetch origin --tags 2>/dev/null || true
git checkout "${TARGET_COMMIT}"

# 3. Build with Apple Silicon Metal acceleration
echo "── [3/3] Building llama-server with Apple Silicon Metal acceleration..."
mkdir -p build/CMakeFiles/4.4.2 build/tools/ui
cmake -B build -DGGML_METAL=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --target llama-ui-embed -j "$(sysctl -n hw.ncpu 2>/dev/null || echo 4)" || true
if [ -f "build/tools/ui/llama-ui-embed" ]; then
    ./build/tools/ui/llama-ui-embed build/tools/ui/ui.cpp build/tools/ui/ui.h 2>/dev/null || true
fi
cmake --build build --target llama-server -j "$(sysctl -n hw.ncpu 2>/dev/null || echo 4)"

SERVER_BIN="${LLAMA_DIR}/build/bin/llama-server"
if [ ! -f "${SERVER_BIN}" ]; then
    SERVER_BIN="${LLAMA_DIR}/build/llama-server"
fi

if [ -f "${SERVER_BIN}" ]; then
    echo ""
    echo "✅ Successfully built: ${SERVER_BIN}"
    echo "Ready to launch with: ./scripts/run_llama_server.sh"
else
    echo ""
    echo "❌ Build completed, but llama-server binary was not found in expected paths."
    exit 1
fi
