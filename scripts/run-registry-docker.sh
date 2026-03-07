#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${ACP_REGISTRY_IMAGE:-acp-registry-tools}"
DOCKERFILE="${ACP_REGISTRY_DOCKERFILE:-$ROOT/docker/registry-tools.Dockerfile}"
BUILD_IMAGE="${ACP_REGISTRY_BUILD_IMAGE:-1}"
STATE_DIR_REL="${ACP_REGISTRY_STATE_DIR:-.docker-state}"
STATE_DIR_HOST="$ROOT/$STATE_DIR_REL"
STATE_DIR_CONTAINER="/workspace/$STATE_DIR_REL"
HOME_DIR_CONTAINER="$STATE_DIR_CONTAINER/home"
UV_CACHE_DIR_CONTAINER="$STATE_DIR_CONTAINER/uv-cache"
NPM_CACHE_DIR_CONTAINER="$STATE_DIR_CONTAINER/npm-cache"
XDG_CACHE_DIR_CONTAINER="$STATE_DIR_CONTAINER/xdg-cache"
XDG_CONFIG_DIR_CONTAINER="$HOME_DIR_CONTAINER/.config"

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 <command> [args...]" >&2
  exit 1
fi

mkdir -p \
  "$STATE_DIR_HOST/home/.config" \
  "$STATE_DIR_HOST/uv-cache" \
  "$STATE_DIR_HOST/npm-cache" \
  "$STATE_DIR_HOST/xdg-cache"

if [[ "$BUILD_IMAGE" == "1" ]]; then
  docker build -f "$DOCKERFILE" -t "$IMAGE" "$ROOT"
fi

exec docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME="$HOME_DIR_CONTAINER" \
  -e UV_CACHE_DIR="$UV_CACHE_DIR_CONTAINER" \
  -e NPM_CONFIG_CACHE="$NPM_CACHE_DIR_CONTAINER" \
  -e XDG_CACHE_HOME="$XDG_CACHE_DIR_CONTAINER" \
  -e XDG_CONFIG_HOME="$XDG_CONFIG_DIR_CONTAINER" \
  -e PYTHONUNBUFFERED=1 \
  -e TERM=dumb \
  -e CI=1 \
  -e PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring \
  -e PYTHON_KEYRING_DISABLED=1 \
  -v "$ROOT:/workspace" \
  -w /workspace \
  "$IMAGE" "$@"
