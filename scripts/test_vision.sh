#!/usr/bin/env bash
# Vision proxy test runner (schema, proxy, cloud path, smoke)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

export PYTHONPATH="${PWD}${PYTHONPATH:+:$PYTHONPATH}"

LIVE_VLM=false
for arg in "$@"; do
  case "$arg" in
    --live) LIVE_VLM=true ;;
  esac
done

echo "→ Vision schema + proxy unit tests"
python -m pytest -q \
  tests/test_vision_schema.py \
  tests/test_vision_proxy.py \
  tests/test_vision_proxy_cloud_path.py \
  tests/test_cloud_payload_integration.py::TestVisionTranscriptionCache \
  -m "not network" \
  --tb=short

echo "→ Vision proxy smoke (pipeline + routing)"
python -m pytest -q \
  tests/test_vision_proxy_smoke.py \
  -m "not network" \
  --tb=short

echo "→ Router image → complex-cloud checks"
python -m pytest -q \
  tests/test_router_properties.py::TestRouteDecisionDomain::test_image_with_frontier_routes_cloud_for_vision_proxy \
  tests/test_router_web_intent.py -k "image" \
  -m "not network" \
  --tb=short

if $LIVE_VLM; then
  echo "→ Live VLM on LM Studio (requires medium model on :1234)"
  python -m pytest -q tests/test_vision_proxy_smoke.py -m network --tb=short || true
else
  echo "→ Skipping live VLM (pass --live to hit LM Studio)"
fi

echo "✓ Vision proxy test suite complete"
