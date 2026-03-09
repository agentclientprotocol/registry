#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
IMAGE="${ACP_REGISTRY_IMAGE:-acp-registry-tools}"
WORKFLOWS_DIR="$ROOT/.github/workflows"
DOCKERFILE="${ACP_REGISTRY_DOCKERFILE:-$WORKFLOWS_DIR/docker/registry-tools.Dockerfile}"
DOCKER_CONTEXT="${ACP_REGISTRY_DOCKER_CONTEXT:-$WORKFLOWS_DIR}"
DOCKER_PLATFORM="${ACP_REGISTRY_DOCKER_PLATFORM:-linux/amd64}"
BUILD_IMAGE="${ACP_REGISTRY_BUILD_IMAGE:-auto}"
STATE_DIR_REL="${ACP_REGISTRY_STATE_DIR:-.docker-state}"
STATE_DIR_HOST="$ROOT/$STATE_DIR_REL"
STATE_DIR_CONTAINER="/workspace/$STATE_DIR_REL"
HOME_DIR_CONTAINER="$STATE_DIR_CONTAINER/home"
UV_CACHE_DIR_CONTAINER="$STATE_DIR_CONTAINER/uv-cache"
NPM_CACHE_DIR_CONTAINER="$STATE_DIR_CONTAINER/npm-cache"
XDG_CACHE_DIR_CONTAINER="$STATE_DIR_CONTAINER/xdg-cache"
XDG_CONFIG_DIR_CONTAINER="$STATE_DIR_CONTAINER/xdg-config"
BUILD_HASH_LABEL="org.openai.acp-registry.build-hash"

hash_cmd() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$@"
    return
  fi

  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$@"
    return
  fi

  echo "Missing SHA-256 command (expected shasum or sha256sum)" >&2
  exit 2
}

compute_build_hash() {
  local file

  {
    for file in "$@"; do
      printf '%s  %s\n' "$(hash_cmd "$file" | awk '{print $1}')" "$file"
    done
  } | hash_cmd | awk '{print $1}'
}

image_platform() {
  docker image inspect "$IMAGE" --format '{{.Os}}/{{.Architecture}}{{if .Variant}}/{{.Variant}}{{end}}'
}

image_build_hash() {
  docker image inspect "$IMAGE" \
    --format '{{range $key, $value := .Config.Labels}}{{printf "%s=%s\n" $key $value}}{{end}}' \
    | awk -F= -v key="$BUILD_HASH_LABEL" '$1 == key { print $2; exit }'
}

image_needs_rebuild() {
  local current_build_hash=""
  local current_platform=""

  if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    return 0
  fi

  if [[ -n "$DOCKER_PLATFORM" ]]; then
    current_platform="$(image_platform 2>/dev/null || true)"
    if [[ "$current_platform" != "$DOCKER_PLATFORM" ]]; then
      return 0
    fi
  fi

  current_build_hash="$(image_build_hash 2>/dev/null || true)"
  if [[ "$current_build_hash" != "$BUILD_HASH" ]]; then
    return 0
  fi

  return 1
}

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 <command> [args...]" >&2
  exit 1
fi

DOCKER_PLATFORM_ARGS=()
if [[ -n "$DOCKER_PLATFORM" ]]; then
  DOCKER_PLATFORM_ARGS=(--platform "$DOCKER_PLATFORM")
fi

IMAGE_INPUT_FILES=("$DOCKERFILE")
if [[ -f "$WORKFLOWS_DIR/docker/registry-entrypoint.sh" ]]; then
  IMAGE_INPUT_FILES+=("$WORKFLOWS_DIR/docker/registry-entrypoint.sh")
fi
BUILD_HASH="$(compute_build_hash "${IMAGE_INPUT_FILES[@]}")"

mkdir -p \
  "$STATE_DIR_HOST/home" \
  "$STATE_DIR_HOST/uv-cache" \
  "$STATE_DIR_HOST/npm-cache" \
  "$STATE_DIR_HOST/xdg-cache" \
  "$STATE_DIR_HOST/xdg-config"

case "$BUILD_IMAGE" in
  1|true|yes)
    SHOULD_BUILD=1
    ;;
  0|false|no)
    SHOULD_BUILD=0
    ;;
  auto)
    if image_needs_rebuild; then
      SHOULD_BUILD=1
    else
      SHOULD_BUILD=0
    fi
    ;;
  *)
    echo "Invalid ACP_REGISTRY_BUILD_IMAGE value: $BUILD_IMAGE" >&2
    echo "Expected one of: auto, 0, 1" >&2
    exit 2
    ;;
esac

if [[ "$SHOULD_BUILD" == "1" ]]; then
  docker build \
    "${DOCKER_PLATFORM_ARGS[@]}" \
    --label "$BUILD_HASH_LABEL=$BUILD_HASH" \
    -f "$DOCKERFILE" \
    -t "$IMAGE" \
    "$DOCKER_CONTEXT"
fi

exec docker run --rm \
  "${DOCKER_PLATFORM_ARGS[@]}" \
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
