#!/usr/bin/env python3
"""
Deterministic script to detect and update agent versions to their latest releases.

Usage:
    # Check for updates (dry run)
    python .github/workflows/update_versions.py

    # Apply updates
    python .github/workflows/update_versions.py --apply

    # Check specific agents
    python .github/workflows/update_versions.py --agents gemini,goose

Environment variables:
    GITHUB_TOKEN: GitHub token for API requests (increases rate limit)
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple

from registry_utils import (
    extract_npm_package_name,
    extract_pypi_package_name,
    load_quarantine,
    should_skip_dir,
)


class VersionUpdate(NamedTuple):
    """Represents a version update for an agent."""

    agent_id: str
    agent_path: Path
    current_version: str
    latest_version: str
    distribution_type: str  # 'npx', 'uvx', 'binary', or combined like 'binary+npx'
    source_url: str  # URL where version was fetched from


class UpdateError(NamedTuple):
    """Represents an error during version checking."""

    agent_id: str
    error: str


# Directories to scan for agents
AGENT_DIRS = [
    ".",  # Root directory (active agents)
]


def get_github_token() -> str | None:
    """Get GitHub token from environment."""
    return os.environ.get("GITHUB_TOKEN")


def make_request(url: str, headers: dict | None = None) -> dict | list | str | None:
    """Make HTTP request and return JSON response."""
    req_headers = {"User-Agent": "ACP-Registry-Version-Checker/1.0"}
    if headers:
        req_headers.update(headers)

    # Add GitHub token if available and this is a GitHub API request
    token = get_github_token()
    if token and "api.github.com" in url:
        req_headers["Authorization"] = f"token {token}"

    try:
        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode("utf-8")
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return content
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if e.code >= 500:
            return None
        raise
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def is_prerelease(version: str) -> bool:
    """Check if a version string is not a stable numeric dotted release."""
    normalized = version.lstrip("v")
    return not bool(re.fullmatch(r"\d+(?:\.\d+)*", normalized))


def normalize_release_version(version: str | None) -> str | None:
    """Normalize comparable release versions to a consistent dotted form."""
    if not version:
        return None
    if re.fullmatch(r"\d+", version):
        return f"{version}.0.0"
    if re.fullmatch(r"\d+\.\d+", version):
        return f"{version}.0"
    return version


def version_sort_key(version: str) -> tuple[int, ...]:
    """Return a sortable key for numeric dotted release versions."""
    normalized = normalize_release_version(version)
    if not normalized or not re.fullmatch(r"\d+(?:\.\d+)*", normalized):
        raise ValueError(f"Unsupported version format: {version}")
    return tuple(int(part) for part in normalized.split("."))


def get_highest_stable_version(versions: set[str]) -> str | None:
    """Return the highest non-prerelease version from a set."""
    stable_versions = {
        normalized
        for version in versions
        if not is_prerelease(version)
        for normalized in [normalize_release_version(version)]
        if normalized is not None
    }
    if not stable_versions:
        return None
    return max(stable_versions, key=version_sort_key)


def get_npm_versions(package_name: str) -> set[str] | None:
    """Get all stable published versions of an npm package."""
    # Handle scoped packages: @scope/name -> %40scope%2Fname
    encoded_name = package_name.replace("@", "%40").replace("/", "%2F")
    url = f"https://registry.npmjs.org/{encoded_name}"
    data = make_request(
        url,
        headers={"Accept": "application/vnd.npm.install-v1+json"},
    )
    if isinstance(data, dict):
        versions = data.get("versions", {})
        if isinstance(versions, dict):
            stable_versions = {
                normalized
                for version in versions
                if not is_prerelease(version)
                for normalized in [normalize_release_version(version)]
                if normalized is not None
            }
            if stable_versions:
                return stable_versions

        dist_tags = data.get("dist-tags", {})
        if isinstance(dist_tags, dict):
            latest = normalize_release_version(dist_tags.get("latest"))
            if latest and not is_prerelease(latest):
                return {latest}
    return None


def get_pypi_versions(package_name: str) -> set[str] | None:
    """Get all stable published versions of a PyPI package."""
    url = f"https://pypi.org/pypi/{package_name}/json"
    data = make_request(url)
    if isinstance(data, dict):
        releases = data.get("releases", {})
        if isinstance(releases, dict):
            stable_versions = set()
            for version, files in releases.items():
                if not files or is_prerelease(version):
                    continue
                if all(isinstance(file, dict) and file.get("yanked", False) for file in files):
                    continue
                normalized = normalize_release_version(version)
                if normalized:
                    stable_versions.add(normalized)
            if stable_versions:
                return stable_versions

        info = data.get("info", {})
        if isinstance(info, dict):
            latest = normalize_release_version(info.get("version"))
            if latest and not is_prerelease(latest):
                return {latest}
    return None


def get_github_latest_release(repo_url: str) -> tuple[str | None, list[str]]:
    """Get latest release version and asset names from GitHub repo.

    Returns: (version, [asset_names])
    """
    # Extract owner/repo from URL
    match = re.search(r"github\.com/([^/]+)/([^/]+)", repo_url)
    if not match:
        return None, []

    owner, repo = match.groups()
    if repo.endswith(".git"):
        repo = repo[:-4]

    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    data = make_request(api_url)

    if isinstance(data, dict):
        tag = data.get("tag_name", "")
        # Strip 'v' prefix if present
        version = normalize_release_version(tag.lstrip("v") if tag else None)
        assets = [a["name"] for a in data.get("assets", [])]
        return version, assets

    return None, []


def get_github_release_versions(repo_url: str) -> set[str] | None:
    """Get stable GitHub release versions published for a repository."""
    match = re.search(r"github\.com/([^/]+)/([^/]+)", repo_url)
    if not match:
        return None

    owner, repo = match.groups()
    if repo.endswith(".git"):
        repo = repo[:-4]

    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=100"
    data = make_request(api_url)
    if isinstance(data, list):
        versions = set()
        for release in data:
            if not isinstance(release, dict):
                continue
            if release.get("draft") or release.get("prerelease"):
                continue
            tag = release.get("tag_name", "")
            version = normalize_release_version(tag.lstrip("v") if tag else None)
            if version and not is_prerelease(version):
                versions.add(version)
        if versions:
            return versions

    latest, _assets = get_github_latest_release(repo_url)
    if latest:
        return {latest}

    return None


def find_all_agents(registry_dir: Path) -> list[tuple[Path, dict]]:
    """Find all agent.json files in the registry, excluding quarantined ones."""
    agents = []
    quarantine = load_quarantine(registry_dir)

    for scan_dir in AGENT_DIRS:
        base_path = registry_dir / scan_dir if scan_dir != "." else registry_dir

        if not base_path.exists():
            continue

        for entry_dir in sorted(base_path.iterdir()):
            if not entry_dir.is_dir():
                continue
            if should_skip_dir(entry_dir.name):
                continue

            agent_json = entry_dir / "agent.json"
            if agent_json.exists():
                try:
                    with open(agent_json) as f:
                        agent_data = json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    print(f"Warning: Could not read {agent_json}: {e}", file=sys.stderr)
                    continue

                agent_id = agent_data.get("id", entry_dir.name)
                if agent_id in quarantine:
                    print(f"  ⊘ Quarantined {agent_id}: {quarantine[agent_id]}", file=sys.stderr)
                    continue

                agents.append((agent_json, agent_data))

    if quarantine:
        print(f"  ({len(quarantine)} agent(s) quarantined)", file=sys.stderr)
        print(file=sys.stderr)

    return agents


def check_agent_version(
    agent_path: Path, agent_data: dict
) -> tuple[VersionUpdate | None, UpdateError | None]:
    """Check if an agent has a newer version available.

    Checks ALL distribution sources and fails if they report different versions.
    """
    agent_id = agent_data.get("id", "unknown")
    current_version = agent_data.get("version", "0.0.0")
    distribution = agent_data.get("distribution", {})
    repository = agent_data.get("repository", "")

    # Collect stable published versions from all distribution sources
    current_version = normalize_release_version(current_version) or current_version
    source_versions: dict[str, tuple[set[str], str]] = {}  # type -> (versions, source_url)

    if "npx" in distribution:
        package_spec = distribution["npx"].get("package", "")
        package_name = extract_npm_package_name(package_spec)
        if not package_name:
            return None, UpdateError(agent_id, "Could not extract npm package name")
        versions = get_npm_versions(package_name)
        if not versions:
            return None, UpdateError(agent_id, f"Could not fetch npm versions for {package_name}")
        source_versions["npx"] = (versions, f"https://registry.npmjs.org/{package_name}")

    if "uvx" in distribution:
        package_spec = distribution["uvx"].get("package", "")
        package_name = extract_pypi_package_name(package_spec)
        if not package_name:
            return None, UpdateError(agent_id, "Could not extract PyPI package name")
        versions = get_pypi_versions(package_name)
        if not versions:
            return None, UpdateError(agent_id, f"Could not fetch PyPI versions for {package_name}")
        source_versions["uvx"] = (versions, f"https://pypi.org/pypi/{package_name}/json")

    if "binary" in distribution and repository and "github.com" in repository:
        versions = get_github_release_versions(repository)
        if not versions:
            return None, UpdateError(
                agent_id,
                f"Could not fetch GitHub releases for {repository}",
            )
        source_versions["binary"] = (versions, repository)

    if not source_versions:
        if distribution:
            return None, None  # Has distributions but none are checkable (e.g. binary without repo)
        return None, UpdateError(agent_id, "Unknown distribution type")

    common_versions: set[str] | None = None
    for versions, _source_url in source_versions.values():
        common_versions = set(versions) if common_versions is None else common_versions & versions

    if not common_versions:
        details = ", ".join(
            f"{dist_type}={get_highest_stable_version(versions) or 'none'}"
            for dist_type, (versions, _) in sorted(source_versions.items())
        )
        return None, UpdateError(agent_id, f"Version mismatch across distributions: {details}")

    latest_version = get_highest_stable_version(common_versions)
    if not latest_version:
        return None, UpdateError(agent_id, "No stable versions found across distributions")
    if latest_version == current_version:
        return None, None  # Up to date

    dist_types = "+".join(sorted(source_versions.keys()))
    primary_source_url = next(iter(source_versions.values()))[1]

    return VersionUpdate(
        agent_id=agent_id,
        agent_path=agent_path,
        current_version=current_version,
        latest_version=latest_version,
        distribution_type=dist_types,
        source_url=primary_source_url,
    ), None


def apply_update(update: VersionUpdate) -> bool:
    """Apply a version update to an agent, updating all distribution types."""
    try:
        with open(update.agent_path) as f:
            agent_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading {update.agent_path}: {e}", file=sys.stderr)
        return False

    old_version = agent_data["version"]
    new_version = update.latest_version
    distribution = agent_data.get("distribution", {})

    # Update version field
    agent_data["version"] = new_version

    # Update npx package spec if present
    if "npx" in distribution:
        package_spec = distribution["npx"].get("package", "")
        package_name = extract_npm_package_name(package_spec)
        distribution["npx"]["package"] = f"{package_name}@{new_version}"

    # Update uvx package spec if present
    if "uvx" in distribution:
        package_spec = distribution["uvx"].get("package", "")
        new_package_spec = re.sub(r"([=@]+)[\d.]+", rf"\g<1>{new_version}", package_spec)
        distribution["uvx"]["package"] = new_package_spec

    # Update binary archive URLs if present
    if "binary" in distribution:
        # For URLs, also handle x.y.0 <-> x.y conversions
        old_short = re.sub(r"\.0$", "", old_version)  # 1.6.0 -> 1.6
        new_short = re.sub(r"\.0$", "", new_version)  # 1.7.0 -> 1.7

        for _platform, target in distribution["binary"].items():
            if "archive" in target:
                original_url = target["archive"]
                url = original_url
                # Replace version in URL path (handles both vX.Y.Z and X.Y.Z patterns)
                url = url.replace(f"/v{old_version}/", f"/v{new_version}/")
                url = url.replace(f"/{old_version}/", f"/{new_version}/")
                url = url.replace(f"-{old_version}.", f"-{new_version}.")
                url = url.replace(f"-{old_version}-", f"-{new_version}-")
                url = url.replace(f"_{old_version}.", f"_{new_version}.")
                url = url.replace(f"_{old_version}_", f"_{new_version}_")
                # Also handle short versions (x.y) in URLs when semver is x.y.0
                # Only apply if the full version wasn't found in the URL, to avoid
                # old_short (e.g. "2.2") matching inside already-replaced new_version
                # (e.g. "-2.2." in "-2.2.1.zip" -> "-2.2.1.1.zip")
                if old_short != old_version and url == original_url:
                    url = url.replace(f"/{old_short}/", f"/{new_short}/")
                    url = url.replace(f"-{old_short}.", f"-{new_short}.")
                    url = url.replace(f"-{old_short}-", f"-{new_short}-")
                target["archive"] = url

    # Write back
    try:
        with open(update.agent_path, "w") as f:
            json.dump(agent_data, f, indent=2)
            f.write("\n")
        return True
    except OSError as e:
        print(f"Error writing {update.agent_path}: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Check and update agent versions in the ACP registry"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates (default is dry-run)",
    )
    parser.add_argument(
        "--agents",
        type=str,
        help="Comma-separated list of agent IDs to check (default: all)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    # Determine registry directory
    registry_dir = Path(__file__).parent.parent.parent

    # Find all agents
    agents = find_all_agents(registry_dir)

    # Filter by agent IDs if specified
    if args.agents:
        filter_ids = set(args.agents.split(","))
        agents = [(p, d) for p, d in agents if d.get("id") in filter_ids]

    # Sort deterministically by agent ID
    agents.sort(key=lambda x: x[1].get("id", ""))

    updates: list[VersionUpdate] = []
    errors: list[UpdateError] = []
    up_to_date: list[str] = []

    # Check each agent
    for agent_path, agent_data in agents:
        agent_id = agent_data.get("id", "unknown")

        if not args.json:
            print(f"Checking {agent_id}...", end=" ", flush=True)

        update, error = check_agent_version(agent_path, agent_data)

        if error:
            errors.append(error)
            if not args.json:
                print(f"ERROR: {error.error}")
        elif update:
            updates.append(update)
            if not args.json:
                print(f"UPDATE: {update.current_version} -> {update.latest_version}")
        else:
            up_to_date.append(agent_id)
            if not args.json:
                print(f"OK ({agent_data.get('version', 'unknown')})")

    # Output results
    if args.json:
        result = {
            "updates": [
                {
                    "agent_id": u.agent_id,
                    "agent_path": str(u.agent_path),
                    "current_version": u.current_version,
                    "latest_version": u.latest_version,
                    "distribution_type": u.distribution_type,
                    "source_url": u.source_url,
                }
                for u in updates
            ],
            "errors": [{"agent_id": e.agent_id, "error": e.error} for e in errors],
            "up_to_date": up_to_date,
        }
        print(json.dumps(result, indent=2))
    else:
        print()
        print("=" * 60)
        print(
            f"Summary: {len(updates)} updates, {len(errors)} errors, {len(up_to_date)} up-to-date"
        )

        if updates:
            print()
            print("Updates available:")
            for u in updates:
                print(
                    f"  - {u.agent_id}: {u.current_version} -> "
                    f"{u.latest_version} ({u.distribution_type})"
                )

        if errors:
            print()
            print("Errors:")
            for e in errors:
                print(f"  - {e.agent_id}: {e.error}")

    # Apply updates if requested
    if args.apply and updates:
        print()
        print("Applying updates...")
        applied = 0
        failed = 0
        for update in updates:
            if not args.json:
                print(f"  Updating {update.agent_id}...", end=" ", flush=True)
            if apply_update(update):
                applied += 1
                if not args.json:
                    print("OK")
            else:
                failed += 1
                if not args.json:
                    print("FAILED")

        print()
        print(f"Applied {applied} updates, {failed} failed")

        # Exit with error if any updates failed
        if failed > 0:
            sys.exit(1)

    # Exit with special code if updates are available (for CI)
    if updates and not args.apply:
        sys.exit(2)  # Updates available but not applied

    if errors:
        sys.exit(1)  # Errors occurred

    sys.exit(0)


if __name__ == "__main__":
    main()
