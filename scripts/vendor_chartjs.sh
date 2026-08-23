#!/usr/bin/env bash
# Downloads pinned Chart.js into assets/vendor/ if missing or VERSION mismatch.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${ROOT}/assets/vendor"
VERSION_FILE="${VENDOR_DIR}/VERSION"
CHART_JS="${VENDOR_DIR}/chart.umd.min.js"
PINNED_VERSION="4.4.1"

mkdir -p "${VENDOR_DIR}"

if [[ -f "${VERSION_FILE}" ]] && [[ "$(cat "${VERSION_FILE}")" == "${PINNED_VERSION}" ]] && [[ -f "${CHART_JS}" ]]; then
  echo "Chart.js ${PINNED_VERSION} already vendored at assets/vendor/chart.umd.min.js"
  exit 0
fi

echo "Downloading Chart.js ${PINNED_VERSION} to assets/vendor/..."
curl -fsSL "https://cdn.jsdelivr.net/npm/chart.js@${PINNED_VERSION}/dist/chart.umd.min.js" \
  -o "${CHART_JS}"
echo "${PINNED_VERSION}" > "${VERSION_FILE}"
echo "Done — Chart.js ${PINNED_VERSION} saved to assets/vendor/"
