"""Shared utilities for ACP registry scripts."""

import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {
    ".claude",
    ".git",
    ".github",
    ".idea",
    "__pycache__",
    "dist",
    ".sandbox",
    ".sparkle-space",
    ".ruff_cache",
}

AGENT_ENV_RESERVED_NAMES = {
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_URL",
    "CI",
    "COMSPEC",
    "DYLD_INSERT_LIBRARIES",
    "GITHUB_ACTION",
    "GITHUB_ACTIONS",
    "GITHUB_ACTOR",
    "GITHUB_API_URL",
    "GITHUB_ENV",
    "GITHUB_EVENT_NAME",
    "GITHUB_EVENT_PATH",
    "GITHUB_GRAPHQL_URL",
    "GITHUB_JOB",
    "GITHUB_OUTPUT",
    "GITHUB_PATH",
    "GITHUB_REF",
    "GITHUB_REPOSITORY",
    "GITHUB_RUN_ID",
    "GITHUB_SERVER_URL",
    "GITHUB_SHA",
    "GITHUB_STEP_SUMMARY",
    "GITHUB_TOKEN",
    "GITHUB_WORKFLOW",
    "GITHUB_WORKSPACE",
    "HOME",
    "LD_PRELOAD",
    "NODE_EXTRA_CA_CERTS",
    "NODE_OPTIONS",
    "NPM_CONFIG_CACHE",
    "NPM_CONFIG_USERCONFIG",
    "NPM_TOKEN",
    "PATH",
    "PATHEXT",
    "PIP_INDEX_URL",
    "PIP_TRUSTED_HOST",
    "PYTHONHOME",
    "PYTHONPATH",
    "REQUESTS_CA_BUNDLE",
    "RUNNER_TEMP",
    "RUNNER_TOOL_CACHE",
    "RUNNER_WORKSPACE",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "SystemRoot",
    "TEMP",
    "TMP",
    "TMPDIR",
    "UV_CACHE_DIR",
    "UV_INDEX_URL",
    "WINDIR",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
}
AGENT_ENV_RESERVED_PREFIXES = (
    "ACTIONS_",
    "AWS_",
    "AZURE_",
    "DYLD_",
    "GCLOUD_",
    "GITHUB_",
    "GOOGLE_",
    "LD_",
    "NODE_",
    "NPM_",
    "PIP_",
    "PYTHON_",
    "RUNNER_",
    "SSH_",
    "UV_",
    "XDG_",
)


def should_skip_dir(name: str) -> bool:
    """Return whether a top-level directory should be skipped during registry scans."""
    return name in SKIP_DIRS or name.startswith(".")


def is_reserved_agent_env_name(name: str) -> bool:
    """Return whether a registry-provided env var would affect runner/process plumbing."""
    normalized = name.strip()
    return normalized in AGENT_ENV_RESERVED_NAMES or normalized.startswith(
        AGENT_ENV_RESERVED_PREFIXES
    )


def sanitize_agent_env(env: dict[str, str] | None) -> dict[str, str]:
    """Drop registry-provided env vars that could expose credentials or alter launch state."""
    if not env:
        return {}
    return {
        name: value
        for name, value in env.items()
        if isinstance(name, str)
        and isinstance(value, str)
        and name
        and not is_reserved_agent_env_name(name)
    }


def subprocess_group_kwargs() -> dict:
    """Return Popen kwargs that isolate spawned agent descendants into their own group."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def terminate_process_group(proc: subprocess.Popen, timeout: float = 2) -> None:
    """Terminate a process and descendants started with subprocess_group_kwargs."""
    if os.name == "nt":
        if proc.poll() is not None:
            return
        proc.terminate()
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except OSError:
            proc.terminate()

    try:
        proc.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass

    if os.name == "nt":
        proc.kill()
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except OSError:
            proc.kill()

    proc.wait(timeout=timeout)


def extract_npm_package_name(package_spec: str) -> str:
    """Extract npm package name from spec like @scope/name@version."""
    if package_spec.startswith("@"):
        at_positions = [i for i, c in enumerate(package_spec) if c == "@"]
        if len(at_positions) > 1:
            return package_spec[: at_positions[1]]
        return package_spec
    return package_spec.split("@")[0]


def extract_npm_package_version(package_spec: str) -> str | None:
    """Extract version from npm package spec like @scope/name@version."""
    if package_spec.startswith("@"):
        at_positions = [i for i, c in enumerate(package_spec) if c == "@"]
        if len(at_positions) > 1:
            return package_spec[at_positions[1] + 1 :]
        return None
    parts = package_spec.split("@")
    return parts[1] if len(parts) > 1 else None


def extract_pypi_package_name(package_spec: str) -> str:
    """Extract PyPI package name from spec like package==version."""
    return re.split(r"[<>=!@]", package_spec)[0]


def normalize_version(version: str) -> str:
    """Normalize version to semver format (x.y.z)."""
    parts = version.split(".")
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts[:3])


def load_quarantine(registry_dir: Path) -> dict[str, str]:
    """Load quarantine list from registry directory.

    Returns:
        Dict mapping agent_id to quarantine reason.
    """
    quarantine_path = registry_dir / "quarantine.json"
    if not quarantine_path.exists():
        return {}
    try:
        with open(quarantine_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: Could not read {quarantine_path}: {e}", file=sys.stderr)
        return {}
