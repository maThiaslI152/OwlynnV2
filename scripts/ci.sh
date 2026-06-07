#!/usr/bin/env bash
# Local CI: run the same checks that used to run on GitHub Actions
# but on your own machine to avoid burning GitHub quota.
#
# Usage:
#   ./scripts/ci.sh            # run everything (unit tests only; no live API)
#   ./scripts/ci.sh --quick    # skip frontend build (still runs vitest)
#   ./scripts/ci.sh --python-only
#   ./scripts/ci.sh --frontend-only
#   ./scripts/ci.sh --network  # also run @pytest.mark.network (needs DEEPSEEK_API_KEY)
#   ./scripts/ci.sh --benchmarks

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

QUICK=false
PYTHON_ONLY=false
FRONTEND_ONLY=false
BENCHMARKS=false
NETWORK=false

for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=true ;;
    --python-only) PYTHON_ONLY=true ;;
    --frontend-only) FRONTEND_ONLY=true ;;
    --benchmarks) BENCHMARKS=true ;;
    --network) NETWORK=true ;;
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

  info "Running Python Linter (ruff)…"
  if python -m ruff check .; then
    pass "Ruff lint checks passed"
  else
    fail "Ruff lint checks failed"; EXIT_CODE=1
  fi

  info "Running Python Formatter Check (ruff format)…"
  if python -m ruff format --check .; then
    pass "Ruff format checks passed"
  else
    fail "Ruff format checks failed"; EXIT_CODE=1
  fi

  info "Running Static Type Checking (mypy)…"
  if python -m mypy src/; then
    pass "Mypy type checks passed"
  else
    fail "Mypy type checks failed"; EXIT_CODE=1
  fi

  info "Running unit tests (excluding network, benchmarks)…"
  if python -m pytest -n auto -q -m "not network and not benchmark" --tb=short --cov=src --cov-report=term; then
    pass "Unit tests passed"
  else
    fail "Unit tests failed"; EXIT_CODE=1
  fi

  info "Running audit / contract / cutover tests…"
  if python -m pytest -n auto -q \
    tests/test_verify_report_fixture.py \
    tests/test_websocket_event_contract.py \
    tests/test_frontend_cutover_serving.py \
    --tb=short --cov=src --cov-report=term; \
  then
    pass "Audit/contract tests passed"
  else
    fail "Audit/contract tests failed"; EXIT_CODE=1
  fi

  if $NETWORK; then
    info "=== DeepSeek network tests (live API) ==="
    if [ -f .env ]; then
      set -a
      # shellcheck disable=SC1091
      source .env
      set +a
    fi
    if [ -f .env.local ]; then
      set -a
      # shellcheck disable=SC1091
      source .env.local
      set +a
    fi
    if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
      warn "DEEPSEEK_API_KEY not set — skipping network tests"
    elif python -m pytest -q -m network \
      tests/test_deepseek_v4_chat_matrix_network.py \
      tests/test_deepseek_cache_network.py \
      --tb=short; then
      pass "DeepSeek network tests passed"
    else
      fail "DeepSeek network tests failed"; EXIT_CODE=1
    fi
  fi

# ── Benchmark checks ───────────────────────────────────
if $BENCHMARKS; then
  info "=== Benchmarks ==="
  info "Running benchmarks (quick mode)…"
  if python tests/benchmarks/run.py --all --quick; then
    pass "Benchmarks passed"
  else
    fail "Benchmarks failed"; EXIT_CODE=1
  fi
  info "Verifying benchmark report is non-empty…"
  if python3 -c "
import json
r = json.load(open('tests/benchmarks/benchmark_report.json'))
assert r['total_entries'] > 0, 'Benchmark report is empty'
"; then
    pass "Benchmark report non-empty"
  else
    fail "Benchmark report is empty"; EXIT_CODE=1
  fi
fi
fi

# ── Frontend checks ──────────────────────────────────────
if ! $PYTHON_ONLY; then
  info "=== Frontend checks ==="

  if [ ! -d frontend-v2/node_modules ]; then
    info "Installing frontend dependencies…"
    (cd frontend-v2 && npm ci)
  fi

  info "Running frontend linting…"
  if (cd frontend-v2 && npm run lint); then
    pass "Frontend linting passed"
  else
    fail "Frontend linting failed"; EXIT_CODE=1
  fi

  info "Running frontend unit tests (vitest)…"
  if (cd frontend-v2 && npx vitest run); then
    pass "Frontend tests passed"
  else
    fail "Frontend tests failed"; EXIT_CODE=1
  fi

  if ! $QUICK; then
    info "Building frontend & Electron app…"
    if (cd frontend-v2 && npm run build); then
      pass "Frontend & Electron build succeeded"
    else
      fail "Frontend & Electron build failed"; EXIT_CODE=1
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
