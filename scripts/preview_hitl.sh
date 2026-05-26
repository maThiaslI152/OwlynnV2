#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# HITL Preview Script
#
# Pushes synthetic HITL interrupts through the dev API endpoint so you
# can preview the frontend UI without interacting with a real LLM agent.
#
# Usage:
#   ./scripts/preview_hitl.sh router            # Router skill ambiguity
#   ./scripts/preview_hitl.sh security           # Security delete_file
#   ./scripts/preview_hitl.sh plan_review        # Plan review approval
#   ./scripts/preview_hitl.sh scope_clarify      # Scope clarification
#   ./scripts/preview_hitl.sh ask_user           # Mid-task ask_user
#   ./scripts/preview_hitl.sh security --ws      # Also open websocat viewer
#
# Requirements:
#   - Backend running (OWLYNN_DEV=1)
#   - curl (always available)
#   - websocat (optional, for --ws mode)
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

VARIANT="${1:-router}"
BASE_URL="${OWLYNN_BASE_URL:-http://127.0.0.1:8000}"
WS_URL="ws://127.0.0.1:8000/ws/chat"

echo "┌──────────────────────────────────────────────┐"
echo "│  HITL Preview — push synthetic interrupt     │"
echo "│  Variant: ${VARIANT}                               "
echo "│  Backend: ${BASE_URL}                           "
echo "└──────────────────────────────────────────────┘"

# Push via dev API
curl -s -X POST "${BASE_URL}/api/dev/hitl/trigger" \
  -H "Content-Type: application/json" \
  -d "{\"variant\": \"${VARIANT}\"}" | python3 -m json.tool

# Optional websocat viewer
if [[ "${2:-}" == "--ws" ]]; then
  if command -v websocat &>/dev/null; then
    echo ""
    echo "Opening websocat viewer — press Ctrl+C to exit"
    # Use a test thread ID
    THREAD_ID="hitl-preview-$(date +%s)"
    websocat "${WS_URL}/${THREAD_ID}"
  else
    echo "websocat not installed. Install with: cargo install websocat"
  fi
fi
