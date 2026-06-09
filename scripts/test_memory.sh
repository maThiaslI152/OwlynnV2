#!/usr/bin/env bash
# Memory orchestration test runner (unit + smoke + optional Redis live check)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

export PYTHONPATH="${PWD}${PYTHONPATH:+:$PYTHONPATH}"

REDIS_LIVE=false
for arg in "$@"; do
  case "$arg" in
    --redis) REDIS_LIVE=true ;;
  esac
done

echo "→ Memory unit + gate tests"
python -m pytest -q \
  tests/test_phase1_memory_orchestration.py \
  tests/test_memory_retrieve_gate.py \
  tests/test_memory_nodes.py \
  tests/test_qdrant_memory_config.py \
  -m "not network" \
  --tb=short

echo "→ Memory orchestration smoke (automated pipeline)"
python -m pytest -q \
  tests/test_memory_orchestration_smoke.py \
  -m "not network" \
  --tb=short

if $REDIS_LIVE; then
  echo "→ Redis live enqueue (requires running Redis)"
  python -m pytest -q \
    tests/test_memory_orchestration_smoke.py::test_redis_enqueue_when_available \
    --tb=short
else
  echo "→ Skipping Redis live test (pass --redis to enable)"
fi

echo "✓ Memory test suite complete"
