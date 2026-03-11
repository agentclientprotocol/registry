#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TABLE_MODE="${ACP_PROTOCOL_MATRIX_TABLE_MODE:-capabilities}"
SKIP_AGENTS="${ACP_PROTOCOL_MATRIX_SKIP_AGENTS:-}"
KEEP_STATE="${ACP_PROTOCOL_MATRIX_KEEP_STATE:-0}"
SANDBOX_DIR="${ACP_PROTOCOL_MATRIX_SANDBOX_DIR:-}"
TEMP_STATE_DIR=""
TEMP_SANDBOX_DIR=""
TEMP_SANDBOX_ROOT="$ROOT/.matrix-sandbox/.tmp"
TEMP_STATE_ROOT="$ROOT/.docker-state/.tmp"

cleanup() {
  if [[ -n "$TEMP_SANDBOX_DIR" ]]; then
    rm -rf "$TEMP_SANDBOX_DIR"
  fi
  if [[ -n "$TEMP_STATE_DIR" ]]; then
    rm -rf "$TEMP_STATE_DIR"
  fi
}

if [[ -z "$SANDBOX_DIR" ]]; then
  if [[ "$KEEP_STATE" == "1" ]]; then
    SANDBOX_DIR=".matrix-sandbox"
  else
    mkdir -p "$TEMP_SANDBOX_ROOT"
    TEMP_SANDBOX_DIR="$(mktemp -d "$TEMP_SANDBOX_ROOT/protocol-matrix-sandbox.XXXXXX")"
    SANDBOX_DIR="${TEMP_SANDBOX_DIR#"$ROOT"/}"
  fi
fi

ARGS=(
  python3
  .github/workflows/protocol_matrix.py
  --sandbox-dir
  "$SANDBOX_DIR"
  --output-dir
  .protocol-matrix
  --init-timeout
  120
  --rpc-timeout
  5
  --table-mode
  "$TABLE_MODE"
)

if [[ -n "$SKIP_AGENTS" ]]; then
  ARGS+=(--skip-agent "$SKIP_AGENTS")
fi

if [[ -z "${ACP_REGISTRY_STATE_DIR:-}" && "$KEEP_STATE" != "1" ]]; then
  mkdir -p "$TEMP_STATE_ROOT"
  TEMP_STATE_DIR="$(mktemp -d "$TEMP_STATE_ROOT/protocol-matrix-state.XXXXXX")"
fi

if [[ -n "$TEMP_SANDBOX_DIR" || -n "$TEMP_STATE_DIR" ]]; then
  trap cleanup EXIT
fi

if [[ -n "$TEMP_STATE_DIR" ]]; then
  export ACP_REGISTRY_STATE_DIR="${TEMP_STATE_DIR#"$ROOT"/}"
fi

"$SCRIPT_DIR/run-registry-docker.sh" "${ARGS[@]}" "$@"
