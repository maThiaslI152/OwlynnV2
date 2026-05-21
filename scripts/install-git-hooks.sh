#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="${REPO_ROOT}/.githooks"

if [[ ! -d "${HOOKS_DIR}" ]]; then
  echo "Error: ${HOOKS_DIR} not found."
  exit 1
fi

echo "No git hooks to install."
echo "To set up hooks in the future, add scripts to .githooks/ and run this script again."
