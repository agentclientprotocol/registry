"""Shared utilities for ACP registry scripts."""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
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


def should_skip_dir(name: str) -> bool:
    """Return whether a top-level directory should be skipped during registry scans."""
    return name in SKIP_DIRS or name.startswith(".")


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


# URL validation: env var lets CI / local runs disable network calls.
SKIP_URL_VALIDATION = os.environ.get("SKIP_URL_VALIDATION", "").lower() in (
    "1",
    "true",
    "yes",
)


def url_exists(url: str, method: str = "HEAD", retries: int = 3) -> bool:
    """Check if a URL exists using HEAD or GET request with retries."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, method=method)
            req.add_header("User-Agent", "ACP-Registry-Validator/1.0")
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.status in (200, 301, 302)
        except urllib.error.HTTPError as e:
            # Some servers don't support HEAD, try GET
            if method == "HEAD" and e.code in (403, 405):
                return url_exists(url, method="GET", retries=retries - attempt)
            if attempt < retries - 1 and e.code in (429, 500, 502, 503, 504):
                time.sleep(2**attempt)
                continue
            return False
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt < retries - 1:
                time.sleep(2**attempt)
                continue
            return False
    return False


def validate_distribution_urls(distribution: dict) -> list[str]:
    """Validate that distribution URLs exist (binary archives, npm, PyPI).

    Returns a list of human-readable error strings (empty on success).
    Honors SKIP_URL_VALIDATION env var.
    """
    if SKIP_URL_VALIDATION:
        return []

    errors = []

    # Check binary archive URLs
    if "binary" in distribution:
        for platform, target in distribution["binary"].items():
            if "archive" in target:
                url = target["archive"]
                if not url_exists(url):
                    errors.append(f"Binary archive URL not accessible for {platform}: {url}")

    # Check npm package URLs (registry.npmjs.org)
    seen_npm = set()
    for dist_type in ("npx",):
        if dist_type in distribution:
            package = distribution[dist_type].get("package", "")
            pkg_name = extract_npm_package_name(package)
            if pkg_name and pkg_name not in seen_npm:
                seen_npm.add(pkg_name)
                npm_url = f"https://registry.npmjs.org/{pkg_name}"
                if not url_exists(npm_url):
                    errors.append(f"npm package not found: {pkg_name}")

    # Check PyPI package URLs
    if "uvx" in distribution:
        package = distribution["uvx"].get("package", "")
        pkg_name = extract_pypi_package_name(package)
        pypi_url = f"https://pypi.org/pypi/{pkg_name}/json"
        if not url_exists(pypi_url):
            errors.append(f"PyPI package not found: {pkg_name}")

    return errors


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
