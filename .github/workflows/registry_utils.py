"""Shared utilities for ACP registry scripts."""

import contextlib
import copy
import json
import os
import re
import signal
import subprocess
import sys
import time
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
AGENT_ENV_RESERVED_NAMES_NORMALIZED = {name.upper() for name in AGENT_ENV_RESERVED_NAMES}
AGENT_ENV_RESERVED_PREFIXES_NORMALIZED = tuple(
    prefix.upper() for prefix in AGENT_ENV_RESERVED_PREFIXES
)

# Preview channel version scheme: X.Y.Z-preview.N
PREVIEW_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)-preview\.(\d+)$")

# Version part of a uvx package spec (`pkg==1.2.3`, `pkg@1.2.3-preview.4`, ...)
UVX_VERSION_PATTERN = r"[\d.]+(?:-preview\.\d+)?"


def should_skip_dir(name: str) -> bool:
    """Return whether a top-level directory should be skipped during registry scans."""
    return name in SKIP_DIRS or name.startswith(".")


def is_reserved_agent_env_name(name: str) -> bool:
    """Return whether a registry-provided env var would affect runner/process plumbing."""
    normalized = name.strip().upper()
    return normalized in AGENT_ENV_RESERVED_NAMES_NORMALIZED or normalized.startswith(
        AGENT_ENV_RESERVED_PREFIXES_NORMALIZED
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


def _posix_process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _wait_for_posix_process_group_exit(proc: subprocess.Popen, pgid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        if proc.poll() is not None:
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=0)

        if not _posix_process_group_exists(pgid):
            return True

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.05, remaining))


def terminate_process_group(proc: subprocess.Popen, timeout: float = 2) -> None:
    """Terminate a process and descendants started with subprocess_group_kwargs."""
    if os.name == "nt":
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=timeout)
            return

    pgid = proc.pid
    group_signaled = False
    try:
        os.killpg(pgid, signal.SIGTERM)
        group_signaled = True
    except ProcessLookupError:
        if proc.poll() is not None:
            return
    except OSError:
        pass

    if not group_signaled:
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=timeout)
            return

    if _wait_for_posix_process_group_exit(proc, pgid, timeout):
        return

    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        if proc.poll() is None:
            proc.kill()

    _wait_for_posix_process_group_exit(proc, pgid, timeout)


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


def normalize_release_version(version: str | None) -> str | None:
    """Normalize comparable release versions to a consistent dotted form."""
    if not version:
        return None
    if re.fullmatch(r"\d+", version):
        return f"{version}.0.0"
    if re.fullmatch(r"\d+\.\d+", version):
        return f"{version}.0"
    return version


def version_tuple(version: str) -> tuple[int, ...]:
    """Return a sortable key for numeric dotted release versions."""
    normalized = normalize_release_version(version)
    if not normalized or not re.fullmatch(r"\d+(?:\.\d+)*", normalized):
        raise ValueError(f"Unsupported version format: {version}")
    return tuple(int(part) for part in normalized.split("."))


def parse_preview_version(version: str) -> tuple[tuple[int, int, int], int] | None:
    """Parse `X.Y.Z-preview.N` into ((X, Y, Z), N); return None for any other shape."""
    match = PREVIEW_VERSION_RE.match(version or "")
    if not match:
        return None
    major, minor, patch, counter = (int(part) for part in match.groups())
    return (major, minor, patch), counter


def is_preview_version(version: str) -> bool:
    """Return whether a version string is an `X.Y.Z-preview.N` prerelease."""
    return parse_preview_version(version) is not None


def semver_sort_key(version: str) -> tuple:
    """Return a total order over `X.Y.Z` and `X.Y.Z-preview.N` version strings.

    A release ranks above its own prereleases (semver 11.3) and prerelease
    counters compare numerically (semver 11.4.1).
    """
    parsed = parse_preview_version(version)
    if parsed is None:
        return (version_tuple(version), 1, 0)
    release, counter = parsed
    return (release, 0, counter)


def strip_preview(agent: dict) -> dict:
    """Return a deep copy of an agent entry with the `preview` block removed."""
    entry = copy.deepcopy(agent)
    entry.pop("preview", None)
    return entry


def resolve_preview_entry(agent: dict) -> dict:
    """Return the preview-channel view of an agent entry; the highest channel wins.

    Falls back to the stable entry when there is no `preview` block or when the
    stable `version` is at or above `preview.version`. Otherwise `version` and
    `distribution` are replaced wholesale by the preview values and the
    `preview` key is dropped, so the result is an ordinary agent entry.
    """
    preview = agent.get("preview")
    if not preview:
        return strip_preview(agent)
    if semver_sort_key(agent["version"]) >= semver_sort_key(preview["version"]):
        return strip_preview(agent)
    entry = copy.deepcopy(agent)
    entry["version"] = preview["version"]
    entry["distribution"] = copy.deepcopy(preview["distribution"])
    entry.pop("preview")
    return entry


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
