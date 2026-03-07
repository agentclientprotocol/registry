#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARGS=(
  python3
  .github/workflows/protocol_matrix.py
  --sandbox-dir
  .matrix-sandbox
  --output-dir
  .protocol-matrix
)

if [[ -n "${ACP_PROTOCOL_MATRIX_SKIP_AGENTS:-}" ]]; then
  ARGS+=(--skip-agent "$ACP_PROTOCOL_MATRIX_SKIP_AGENTS")
fi

exec "$SCRIPT_DIR/run-registry-docker.sh" "${ARGS[@]}" "$@"
