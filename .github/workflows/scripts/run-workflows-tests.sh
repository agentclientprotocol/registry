#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/run-registry-docker.sh" \
  /bin/sh -lc 'cd /workspace/.github/workflows && uv run --no-project --with pytest pytest tests/ -v "$@"' \
  run-workflows-tests "$@"
