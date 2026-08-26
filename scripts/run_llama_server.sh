#!/bin/bash
# =============================================================================
# Run llama-server with Gemma 4 MTP Speculative Decoding (Verified build b9553)
# =============================================================================
# Author tuning defaults:
#   - Temperature: 0.1 (low for agentic stability / deterministic coding)
#   - Top-P: 0.95
#   - Top-K: 64
#   - Repetition Penalty: 1.1
#   - Flash Attention: enabled (-fa on)
#   - GPU Offload: 100% (-ngl 99, Apple Silicon Metal)
#   - Context Window: 16384 tokens
#   - Speculative draft: gemma-4-12B-it-MTP-Q8_0.gguf / gemma-4-12B-it-MTP-F16.gguf (~88 -> ~180 tok/s)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LLAMA_DIR="${ROOT_DIR}/llama.cpp"

SERVER_BIN="${LLAMA_DIR}/build/bin/llama-server"
if [ ! -f "${SERVER_BIN}" ]; then
    SERVER_BIN="${LLAMA_DIR}/build/llama-server"
fi

if [ ! -f "${SERVER_BIN}" ]; then
    echo "⚠️ llama-server binary not found at ${SERVER_BIN}."
    echo "Building verified llama.cpp (b9553)..."
    bash "${SCRIPT_DIR}/setup_llama_cpp.sh"
    if [ ! -f "${SERVER_BIN}" ]; then
        SERVER_BIN="${LLAMA_DIR}/build/bin/llama-server"
    fi
fi

# Locate Main Model
MAIN_MODEL="${MODEL_PATH:-}"
if [ -z "${MAIN_MODEL}" ] || [ ! -f "${MAIN_MODEL}" ]; then
    CANDIDATES=(
        "${HOME}/Documents/LM Studio/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF/gemma4-v2-Q4_K_M.gguf"
        "/Volumes/KNV3_1TB/LM Studio Model/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF/gemma4-v2-Q4_K_M.gguf"
        "${ROOT_DIR}/.models/gemma4-v2-Q4_K_M.gguf"
        "${HOME}/.lmstudio/models/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF/gemma4-v2-Q4_K_M.gguf"
    )
    for c in "${CANDIDATES[@]}"; do
        if [ -f "$c" ]; then
            MAIN_MODEL="$c"
            break
        fi
    done
fi

if [ -z "${MAIN_MODEL}" ] || [ ! -f "${MAIN_MODEL}" ]; then
    echo "❌ Error: Could not locate main model GGUF (gemma4-v2-Q4_K_M.gguf)."
    echo "Please set MODEL_PATH=/path/to/gemma4-v2-Q4_K_M.gguf and try again."
    exit 1
fi

# Locate Draft Model (MTP)
DRAFT_MODEL="${DRAFT_PATH:-}"
if [ -z "${DRAFT_MODEL}" ] || [ ! -f "${DRAFT_MODEL}" ]; then
    DRAFT_CANDIDATES=(
        "${HOME}/Documents/LM Studio/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF/gemma-4-12B-it-MTP-Q8_0.gguf"
        "${HOME}/Documents/LM Studio/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF/gemma-4-12B-it-MTP-F16.gguf"
        "/Volumes/KNV3_1TB/LM Studio Model/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF/gemma-4-12B-it-MTP-Q8_0.gguf"
        "/Volumes/KNV3_1TB/LM Studio Model/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF/gemma-4-12B-it-MTP-F16.gguf"
        "${ROOT_DIR}/.models/gemma-4-12B-it-MTP-Q8_0.gguf"
        "${ROOT_DIR}/.models/gemma-4-12B-it-MTP-F16.gguf"
    )
    for d in "${DRAFT_CANDIDATES[@]}"; do
        if [ -f "$d" ]; then
            DRAFT_MODEL="$d"
            break
        fi
    done
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-1234}"
CTX_SIZE="${CTX_SIZE:-16384}"
N_GPU_LAYERS="${N_GPU_LAYERS:-99}"
MODEL_ALIAS="gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m"

echo "══════════════════════════════════════════════════════════════"
echo "  Owlynn — llama-server (Gemma 4 12B Unified Agentic Engine)"
echo "══════════════════════════════════════════════════════════════"
echo "  • Server Binary : ${SERVER_BIN}"
echo "  • Main Model    : ${MAIN_MODEL}"
if [ -n "${DRAFT_MODEL}" ] && [ -f "${DRAFT_MODEL}" ]; then
    echo "  • MTP Draft     : ${DRAFT_MODEL} (Speculative decoding ACTIVE)"
else
    echo "  • MTP Draft     : None (Standard decoding)"
fi
echo "  • Endpoint      : http://${HOST}:${PORT}/v1"
echo "  • Context Window: ${CTX_SIZE} tokens"
echo "  • Metal Layers  : ${N_GPU_LAYERS} (All GPU)"
echo "  • Tuning Presets: Top-P=0.95 | Top-K=64 | Repeat-Penalty=1.1 | Jinja=ON"
echo "══════════════════════════════════════════════════════════════"

# Assemble CLI arguments
ARGS=(
    "-m" "${MAIN_MODEL}"
    "-c" "${CTX_SIZE}"
    "-ngl" "${N_GPU_LAYERS}"
    "-fa" "on"
    "-fit" "off"
    "--top-p" "0.95"
    "--top-k" "64"
    "--repeat-penalty" "1.1"
    "--jinja"
    "--reasoning-format" "deepseek"
    "--alias" "${MODEL_ALIAS}"
    "--host" "${HOST}"
    "--port" "${PORT}"
)

# Append MTP Draft if available
if [ -n "${DRAFT_MODEL}" ] && [ -f "${DRAFT_MODEL}" ]; then
    ARGS+=(
        "-md" "${DRAFT_MODEL}"
        "--spec-type" "draft-mtp"
        "--spec-draft-n-max" "16"
        "--spec-draft-n-min" "1"
        "--spec-draft-p-min" "0.75"
        "--spec-draft-ngl" "auto"
    )
fi

# Pass any extra command line flags
ARGS+=("$@")

exec "${SERVER_BIN}" "${ARGS[@]}"
