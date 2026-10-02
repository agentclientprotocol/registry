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

    # Check one release channel only ('stable' or 'preview')
    python .github/workflows/update_versions.py --channels preview

Environment variables:
    GITHUB_TOKEN: GitHub token for API requests (increases rate limit)
"""

import argparse
import json
import re
import sys
from pathlib import Path

from common import (
    CHANNELS,
    LatestRelease,
    PublishedVersions,
    ResolvedAsset,
    UpdateError,
    VersionUpdate,
)
from custom_agent_sources import CustomSourceFn, junie
from github_api import (
    get_github_release_digests,
    get_github_release_versions,
    is_github_repo,
    make_request,
)
from registry_utils import (
    UVX_VERSION_PATTERN,
    extract_npm_package_name,
    extract_pypi_package_name,
    is_prerelease,
    is_preview_version,
    load_quarantine,
    normalize_release_version,
    semver_sort_key,
    should_skip_dir,
    version_tuple,
)

# Directories to scan for agents
AGENT_DIRS = [
    ".",  # Root directory (active agents)
]

# Per-(agent_id, channel) overrides for agents whose releases can't be
# discovered through npm/PyPI/GitHub Releases. See custom_agent_sources/__init__.py.
CUSTOM_AGENT_SOURCES: dict[tuple[str, str], CustomSourceFn] = {
    ("junie", "preview"): junie.get_preview_release,
}


def version_sort_key(version: str) -> tuple[int, ...]:
    """Return a sortable key for numeric dotted release versions."""
    return version_tuple(version)


def get_stable_versions(versions: set[str]) -> set[str]:
    """Return the normalized non-prerelease subset of a published version set."""
    return {
        normalized
        for version in versions
        if not is_prerelease(version)
        for normalized in [normalize_release_version(version)]
        if normalized is not None
    }


def get_highest_stable_version(versions: set[str]) -> str | None:
    """Return the highest non-prerelease version from a set."""
    stable_versions = get_stable_versions(versions)
    if not stable_versions:
        return None
    return max(stable_versions, key=version_sort_key)


def get_highest_preview_version(versions: set[str]) -> str | None:
    """Return the highest `X.Y.Z-preview.N` version from a set."""
    preview_versions = [version for version in versions if is_preview_version(version)]
    if not preview_versions:
        return None
    return max(preview_versions, key=semver_sort_key)


def get_npm_versions(package_name: str) -> set[str] | None:
    """Get all published versions of an npm package, prereleases included.

    Callers partition the result per channel; the `dist-tags.latest` fallback
    stays stable-only so a preview published without `--tag preview` can never
    surface as a stable release.
    """
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
            published_versions = {
                normalized
                for version in versions
                for normalized in [normalize_release_version(version)]
                if normalized is not None
            }
            if published_versions:
                return published_versions

        dist_tags = data.get("dist-tags", {})
        if isinstance(dist_tags, dict):
            latest = normalize_release_version(dist_tags.get("latest"))
            if latest and not is_prerelease(latest):
                return {latest}
    return None


def get_pypi_versions(package_name: str) -> set[str] | None:
    """Get all published versions of a PyPI package, prereleases included."""
    url = f"https://pypi.org/pypi/{package_name}/json"
    data = make_request(url)
    if isinstance(data, dict):
        releases = data.get("releases", {})
        if isinstance(releases, dict):
            published_versions = set()
            for version, files in releases.items():
                if not files:
                    continue
                if all(isinstance(file, dict) and file.get("yanked", False) for file in files):
                    continue
                normalized = normalize_release_version(version)
                if normalized:
                    published_versions.add(normalized)
            if published_versions:
                return published_versions

        info = data.get("info", {})
        if isinstance(info, dict):
            latest = normalize_release_version(info.get("version"))
            if latest and not is_prerelease(latest):
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


def fetch_distribution_versions(
    agent_id: str,
    distribution: dict,
    repository: str,
    cache: dict[str, set[str] | None] | None = None,
) -> tuple[dict[str, PublishedVersions], UpdateError | None]:
    """Fetch the published version list once per declared distribution source.

    Returns a `{distribution_type: PublishedVersions}` mapping. `cache` (keyed
    by source URL) lets one agent check reuse a fetch across channels.
    """
    if cache is None:
        cache = {}
    source_versions: dict[str, PublishedVersions] = {}

    def fetch(source_url: str, fetcher) -> set[str] | None:
        if source_url not in cache:
            cache[source_url] = fetcher()
        return cache[source_url]

    if "npx" in distribution:
        package_spec = distribution["npx"].get("package", "")
        package_name = extract_npm_package_name(package_spec)
        if not package_name:
            return {}, UpdateError(agent_id, "Could not extract npm package name")
        source_url = f"https://registry.npmjs.org/{package_name}"
        versions = fetch(source_url, lambda: get_npm_versions(package_name))
        if not versions:
            return {}, UpdateError(agent_id, f"Could not fetch npm versions for {package_name}")
        source_versions["npx"] = PublishedVersions(versions, source_url)

    if "uvx" in distribution:
        package_spec = distribution["uvx"].get("package", "")
        package_name = extract_pypi_package_name(package_spec)
        if not package_name:
            return {}, UpdateError(agent_id, "Could not extract PyPI package name")
        source_url = f"https://pypi.org/pypi/{package_name}/json"
        versions = fetch(source_url, lambda: get_pypi_versions(package_name))
        if not versions:
            return {}, UpdateError(agent_id, f"Could not fetch PyPI versions for {package_name}")
        source_versions["uvx"] = PublishedVersions(versions, source_url)

    if "binary" in distribution and is_github_repo(repository):
        versions = fetch(repository, lambda: get_github_release_versions(repository))
        if not versions:
            return {}, UpdateError(
                agent_id,
                f"Could not fetch GitHub releases for {repository}",
            )
        source_versions["binary"] = PublishedVersions(versions, repository)

    return source_versions, None


def resolve_update(
    agent_id: str,
    agent_path: Path,
    current_version: str,
    channel: str,
    release: LatestRelease | None,
) -> VersionUpdate | None:
    """Compare a source's reported latest release against the agent's current version.

    The single place that decides "is this actually an update", whether
    `release` came from the standard resolution or a CUSTOM_AGENT_SOURCES override.
    """
    if release is None or release.version == current_version:
        return None
    return VersionUpdate(
        agent_id=agent_id,
        agent_path=agent_path,
        current_version=current_version,
        latest_version=release.version,
        distribution_type=release.distribution_type,
        source_url=release.source_url,
        repository=release.repository,
        channel=channel,
        resolved_assets=release.resolved_assets,
    )


def check_agent_version(
    agent_path: Path,
    agent_data: dict,
    cache: dict[str, set[str] | None] | None = None,
) -> tuple[VersionUpdate | None, UpdateError | None]:
    """Check if an agent has a newer stable version available.

    Checks ALL distribution sources and fails if they report different versions.
    """
    agent_id = agent_data.get("id", "unknown")
    current_version = agent_data.get("version", "0.0.0")
    current_version = normalize_release_version(current_version) or current_version

    override = CUSTOM_AGENT_SOURCES.get((agent_id, "stable"))
    if override:
        release, error = override(agent_data)
        if error:
            return None, error
        return resolve_update(agent_id, agent_path, current_version, "stable", release), None

    distribution = agent_data.get("distribution", {})
    repository = agent_data.get("repository", "")

    published_versions, error = fetch_distribution_versions(
        agent_id, distribution, repository, cache
    )
    if error:
        return None, error

    if not published_versions:
        if distribution:
            return None, None  # Has distributions but none are checkable (e.g. binary without repo)
        return None, UpdateError(agent_id, "Unknown distribution type")

    # Keep the stable channel on stable releases only
    source_versions = {
        dist_type: PublishedVersions(get_stable_versions(pv.versions), pv.source_url)
        for dist_type, pv in published_versions.items()
    }

    common_versions: set[str] | None = None
    for pv in source_versions.values():
        common_versions = (
            set(pv.versions) if common_versions is None else common_versions & pv.versions
        )

    if not common_versions:
        details = ", ".join(
            f"{dist_type}={get_highest_stable_version(pv.versions) or 'none'}"
            for dist_type, pv in sorted(source_versions.items())
        )
        return None, UpdateError(agent_id, f"Version mismatch across distributions: {details}")

    latest_version = get_highest_stable_version(common_versions)
    if not latest_version:
        return None, UpdateError(agent_id, "No stable versions found across distributions")

    dist_types = "+".join(sorted(source_versions.keys()))
    primary_source_url = next(iter(source_versions.values())).source_url

    release = LatestRelease(
        version=latest_version,
        distribution_type=dist_types,
        source_url=primary_source_url,
        repository=repository,
    )
    return resolve_update(agent_id, agent_path, current_version, "stable", release), None


def check_agent_preview_version(
    agent_path: Path,
    agent_data: dict,
    cache: dict[str, set[str] | None] | None = None,
) -> tuple[VersionUpdate | None, UpdateError | None]:
    """Check if an agent has a newer version available on its preview channel.

    The candidate is the highest of the published preview and stable releases,
    so preview users get the newest version either channel has - including a
    plain release once stable overtakes the preview line. Only the
    distribution types declared inside `preview.distribution` take part.

    A CUSTOM_AGENT_SOURCES override for this agent's preview channel, if
    present, replaces this standard resolution entirely - even for an agent
    with no `preview` block yet (compared against a "0.0.0" placeholder).
    """
    agent_id = agent_data.get("id", "unknown")
    preview = agent_data.get("preview")

    override = CUSTOM_AGENT_SOURCES.get((agent_id, "preview"))
    if override:
        release, error = override(agent_data)
        if error:
            return None, error._replace(error=f"preview: {error.error}")
        current_version = preview.get("version", "0.0.0") if isinstance(preview, dict) else "0.0.0"
        return resolve_update(agent_id, agent_path, current_version, "preview", release), None

    if not isinstance(preview, dict):
        return None, None

    current_version = preview.get("version", "0.0.0")
    distribution = preview.get("distribution", {})
    repository = agent_data.get("repository", "")

    published_versions, error = fetch_distribution_versions(
        agent_id, distribution, repository, cache
    )
    if error:
        return None, error._replace(error=f"preview: {error.error}")
    if not published_versions:
        return None, None

    common_versions: set[str] | None = None
    for pv in published_versions.values():
        common_versions = (
            set(pv.versions) if common_versions is None else common_versions & pv.versions
        )

    candidates = [
        candidate
        for candidate in (
            get_highest_preview_version(common_versions or set()),
            get_highest_stable_version(common_versions or set()),
        )
        if candidate
    ]
    if not candidates:
        return None, None  # Nothing published to point at; stay put

    latest_version = max(candidates, key=semver_sort_key)
    dist_types = "+".join(sorted(published_versions.keys()))
    primary_source_url = next(iter(published_versions.values())).source_url

    release = LatestRelease(
        version=latest_version,
        distribution_type=dist_types,
        source_url=primary_source_url,
        repository=repository,
    )
    return resolve_update(agent_id, agent_path, current_version, "preview", release), None


def write_agent_data(agent_path: Path, agent_data: dict) -> bool:
    """Write an agent manifest back to disk in the registry's canonical format."""
    try:
        with open(agent_path, "w") as f:
            json.dump(agent_data, f, indent=2)
            f.write("\n")
        return True
    except OSError as e:
        print(f"Error writing {agent_path}: {e}", file=sys.stderr)
        return False


def update_package_specs(distribution: dict, new_version: str) -> None:
    """Rewrite npx/uvx package specs in place so they pin `new_version`."""
    if "npx" in distribution:
        package_spec = distribution["npx"].get("package", "")
        package_name = extract_npm_package_name(package_spec)
        distribution["npx"]["package"] = f"{package_name}@{new_version}"

    if "uvx" in distribution:
        package_spec = distribution["uvx"].get("package", "")
        distribution["uvx"]["package"] = re.sub(
            rf"([=@]+){UVX_VERSION_PATTERN}", rf"\g<1>{new_version}", package_spec
        )


def _apply_resolved_assets(
    binary_block: dict, resolved_assets: dict[str, ResolvedAsset], agent_id: str
) -> None:
    """Write pre-resolved archive URL + sha256 into existing binary targets.

    Only fills platforms that already have an entry, preserving their
    existing `cmd`/`args`. Skips (with a warning) any platform with no entry.
    """
    for platform, asset in resolved_assets.items():
        target = binary_block.get(platform)
        if target is None:
            print(
                f"WARN: no existing binary target for {agent_id} ({platform}); skipping",
                file=sys.stderr,
            )
            continue
        target["archive"] = asset.archive_url
        target["sha256"] = asset.sha256


def apply_update(update: VersionUpdate) -> bool:
    """Apply a version update to an agent, updating all distribution types."""
    try:
        with open(update.agent_path) as f:
            agent_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading {update.agent_path}: {e}", file=sys.stderr)
        return False

    new_version = update.latest_version

    if update.channel == "preview":
        # Preview bumps touch the preview block only; the stable entry is untouched.
        preview = agent_data.get("preview")
        if not isinstance(preview, dict):
            print(f"Error: {update.agent_path} has no 'preview' block", file=sys.stderr)
            return False
        preview["version"] = new_version
        preview_distribution = preview.get("distribution", {})
        if update.resolved_assets:
            _apply_resolved_assets(
                preview_distribution.get("binary", {}), update.resolved_assets, update.agent_id
            )
        else:
            update_package_specs(preview_distribution, new_version)
        return write_agent_data(update.agent_path, agent_data)

    old_version = agent_data["version"]
    distribution = agent_data.get("distribution", {})

    # Update version field
    agent_data["version"] = new_version

    # Update npx/uvx package specs if present
    update_package_specs(distribution, new_version)

    if update.resolved_assets:
        _apply_resolved_assets(
            distribution.get("binary", {}), update.resolved_assets, update.agent_id
        )
    elif "binary" in distribution:
        # For URLs, also handle x.y.0 <-> x.y conversions
        old_short = re.sub(r"\.0$", "", old_version)  # 1.6.0 -> 1.6
        new_short = re.sub(r"\.0$", "", new_version)  # 1.7.0 -> 1.7

        is_github_repository = is_github_repo(update.repository)
        asset_digests: dict[str, str] | None = None

        for platform_name, target in distribution["binary"].items():
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

                if is_github_repository:
                    if asset_digests is None:
                        asset_digests = get_github_release_digests(update.repository, new_version)
                    digest = asset_digests.get(url.rsplit("/", 1)[-1])
                    if digest:
                        target["sha256"] = digest
                    else:
                        print(
                            f"WARN: no release digest for {update.agent_id} ({platform_name})",
                            file=sys.stderr,
                        )

    return write_agent_data(update.agent_path, agent_data)


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
    parser.add_argument(
        "--channels",
        type=str,
        default=",".join(CHANNELS),
        help=f"Comma-separated release channels to check (default: {','.join(CHANNELS)})",
    )
    args = parser.parse_args()

    channels = [c.strip() for c in args.channels.split(",") if c.strip()]
    unknown_channels = [c for c in channels if c not in CHANNELS]
    if unknown_channels or not channels:
        parser.error(f"--channels must be a subset of {','.join(CHANNELS)}")

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

    checkers = {
        "stable": check_agent_version,
        "preview": check_agent_preview_version,
    }

    # Check each agent
    for agent_path, agent_data in agents:
        agent_id = agent_data.get("id", "unknown")

        if not args.json:
            print(f"Checking {agent_id}...", end=" ", flush=True)

        # One fetch per distribution source, shared by every channel
        fetch_cache: dict[str, set[str] | None] = {}
        agent_updates: list[VersionUpdate] = []
        agent_errors: list[UpdateError] = []

        for channel in CHANNELS:
            if channel not in channels:
                continue
            update, error = checkers[channel](agent_path, agent_data, fetch_cache)
            if error:
                agent_errors.append(error)
            elif update:
                agent_updates.append(update)

        updates.extend(agent_updates)
        errors.extend(agent_errors)
        if not agent_updates and not agent_errors:
            up_to_date.append(agent_id)

        if not args.json:
            messages = [f"ERROR: {e.error}" for e in agent_errors]
            messages += [
                f"UPDATE [{u.channel}]: {u.current_version} -> {u.latest_version}"
                for u in agent_updates
            ]
            if not messages:
                messages.append(f"OK ({agent_data.get('version', 'unknown')})")
            print("; ".join(messages))

    # Output results
    if args.json:
        result = {
            "updates": [
                {
                    "agent_id": u.agent_id,
                    "agent_path": str(u.agent_path),
                    "channel": u.channel,
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
                    f"  - {u.agent_id} ({u.channel}): {u.current_version} -> "
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
