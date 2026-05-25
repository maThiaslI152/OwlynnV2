#!/usr/bin/env bash
# Local CI: run the same checks that used to run on GitHub Actions
# but on your own machine to avoid burning GitHub quota.
#
# Usage:
#   ./scripts/ci.sh          # run everything
#   ./scripts/ci.sh --quick  # skip frontend build (still runs vitest)
#   ./scripts/ci.sh --python-only
#   ./scripts/ci.sh --frontend-only

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

QUICK=false
PYTHON_ONLY=false
FRONTEND_ONLY=false

for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=true ;;
    --python-only) PYTHON_ONLY=true ;;
    --frontend-only) FRONTEND_ONLY=true ;;
  esac
done

# ── Colours ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'
pass() { echo -e " ${GREEN}✓${NC} $1"; }
fail() { echo -e " ${RED}✗${NC} $1"; }
info() { echo -e " ${CYAN}→${NC} $1"; }
warn() { echo -e " ${YELLOW}⚠${NC} $1"; }

EXIT_CODE=0

# ── Python checks ────────────────────────────────────────
if ! $FRONTEND_ONLY; then
  info "=== Python checks ==="

  # Verify dependencies are installed
  if ! python -c "import pytest" 2>/dev/null; then
    warn "pytest not found — installing dependencies..."
    python -m pip install -r requirements.txt -r requirements-dev.txt
  fi

  info "Running unit tests (excluding network, benchmarks)…"
  if python -m pytest -q -m "not network and not benchmark" --tb=short; then
    pass "Unit tests passed"
  else
    fail "Unit tests failed"; EXIT_CODE=1
  fi

  info "Running audit / contract / cutover tests…"
  if python -m pytest -q \
    tests/test_verify_report_fixture.py \
    tests/test_websocket_event_contract.py \
    tests/test_frontend_cutover_serving.py \
    --tb=short; \
  then
    pass "Audit/contract tests passed"
  else
    fail "Audit/contract tests failed"; EXIT_CODE=1
  fi
fi

# ── Frontend checks ──────────────────────────────────────
if ! $PYTHON_ONLY; then
  info "=== Frontend checks ==="

  if [ ! -d frontend-v2/node_modules ]; then
    info "Installing frontend dependencies…"
    (cd frontend-v2 && npm ci)
  fi

  info "Running frontend unit tests (vitest)…"
  if (cd frontend-v2 && npx vitest run); then
    pass "Frontend tests passed"
  else
    fail "Frontend tests failed"; EXIT_CODE=1
  fi

  if ! $QUICK; then
    info "Building frontend…"
    if (cd frontend-v2 && npm run build); then
      pass "Frontend build succeeded"
    else
      fail "Frontend build failed"; EXIT_CODE=1
    fi
  else
    info "Skipping frontend build (--quick)"
  fi
fi

# ── Summary ──────────────────────────────────────────────
echo ""
if [ "$EXIT_CODE" -eq 0 ]; then
  echo -e "${GREEN}All checks passed.${NC}"
else
  echo -e "${RED}Some checks failed.${NC}"
fi

exit "$EXIT_CODE"
