#!/usr/bin/env bash
# Memory orchestration test runner (unit + smoke + optional Postgres live check)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

export PYTHONPATH="${PWD}${PYTHONPATH:+:$PYTHONPATH}"

POSTGRES_LIVE=false
for arg in "$@"; do
  case "$arg" in
    --postgres|--redis) POSTGRES_LIVE=true ;;
  esac
done

echo "→ Memory unit + gate tests"
python -m pytest -q \
  tests/test_phase1_memory_orchestration.py \
  tests/test_memory_retrieve_gate.py \
  tests/test_memory_nodes.py \
  tests/test_pgvector_memory_config.py \
  -m "not network" \
  --tb=short

echo "→ Memory orchestration smoke (automated pipeline)"
python -m pytest -q \
  tests/test_memory_orchestration_smoke.py \
  -m "not network" \
  --tb=short

if $POSTGRES_LIVE; then
  echo "→ Postgres live enqueue (requires running Postgres)"
  python -m pytest -q \
    tests/test_memory_orchestration_smoke.py::test_postgres_enqueue_when_available \
    --tb=short
else
  echo "→ Skipping Postgres live test (pass --postgres to enable)"
fi

echo "✓ Memory test suite complete"
