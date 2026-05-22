#!/usr/bin/env python3
"""Backfill registry-archive.json from published GitHub release snapshots.

This script downloads historical ``registry.json`` assets from published GitHub
releases and merges them into a single archive grouped by agent id.

Usage:
    python .github/workflows/backfill_registry_archive.py

    python .github/workflows/backfill_registry_archive.py \
      --output /tmp/registry-archive.json

Environment variables:
    GITHUB_TOKEN: Optional GitHub token for the releases API.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple

from registry_archive import build_archive_from_snapshots

DEFAULT_REPOSITORY = "agentclientprotocol/registry"
DEFAULT_OUTPUT_NAME = "registry-archive.json"
GITHUB_API_BASE_URL = "https://api.github.com"
USER_AGENT = "ACP-Registry-Archive-Backfill/1.0"


class ReleaseSnapshot(NamedTuple):
    """Published registry snapshot metadata."""

    tag_name: str
    published_at: str
    download_url: str


def get_github_token() -> str | None:
    """Return GitHub token from the environment if present."""
    return os.environ.get("GITHUB_TOKEN")


def request_json(url: str) -> dict | list:
    """Fetch and decode JSON from a URL."""
    headers = {"User-Agent": USER_AGENT}
    token = get_github_token()
    if token and "api.github.com" in url:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read())


def find_registry_asset_url(release: dict) -> str | None:
    """Return the download URL for the registry.json asset in a release."""
    assets = release.get("assets", [])
    if not isinstance(assets, list):
        raise ValueError("Release assets payload must be a list")

    for asset in assets:
        if asset.get("name") == "registry.json":
            download_url = asset.get("browser_download_url")
            if not isinstance(download_url, str) or not download_url:
                raise ValueError("registry.json asset is missing browser_download_url")
            return download_url
    return None


def fetch_release_snapshots(repository: str) -> list[ReleaseSnapshot]:
    """Fetch published releases that contain a registry.json asset."""
    snapshots: list[ReleaseSnapshot] = []
    page = 1

    while True:
        url = f"{GITHUB_API_BASE_URL}/repos/{repository}/releases?per_page=100&page={page}"
        payload = request_json(url)
        if not isinstance(payload, list):
            raise ValueError("GitHub releases API returned a non-list payload")
        if not payload:
            break

        for release in payload:
            if release.get("draft") or release.get("prerelease"):
                continue

            download_url = find_registry_asset_url(release)
            if not download_url:
                continue

            tag_name = release.get("tag_name")
            published_at = release.get("published_at")
            if not isinstance(tag_name, str) or not tag_name:
                raise ValueError("Published release is missing tag_name")
            if not isinstance(published_at, str) or not published_at:
                raise ValueError(f"Release {tag_name} is missing published_at")

            snapshots.append(
                ReleaseSnapshot(
                    tag_name=tag_name,
                    published_at=published_at,
                    download_url=download_url,
                )
            )

        page += 1

    snapshots.sort(key=lambda snapshot: (snapshot.published_at, snapshot.tag_name))
    return snapshots


def fetch_registry_snapshot(snapshot: ReleaseSnapshot) -> dict:
    """Download a published registry.json snapshot."""
    payload = request_json(snapshot.download_url)
    if not isinstance(payload, dict):
        raise ValueError(f"{snapshot.tag_name} registry.json is not a JSON object")

    agents = payload.get("agents")
    if not isinstance(agents, list):
        raise ValueError(f"{snapshot.tag_name} registry.json is missing an agents list")

    return payload


def get_default_output_path() -> Path:
    """Return the default output path under dist/."""
    registry_dir = Path(__file__).parent.parent.parent
    return registry_dir / "dist" / DEFAULT_OUTPUT_NAME


def write_archive(output_path: Path, archive: dict) -> None:
    """Write the archive JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(archive, indent=2) + "\n")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Backfill registry-archive.json from published release snapshots"
    )
    parser.add_argument(
        "--repository",
        default=DEFAULT_REPOSITORY,
        help=f"GitHub repository in owner/name form (default: {DEFAULT_REPOSITORY})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=get_default_output_path(),
        help="Path to write registry-archive.json",
    )
    return parser.parse_args()


def main() -> int:
    """Run the backfill process."""
    args = parse_args()

    snapshots = fetch_release_snapshots(args.repository)
    if not snapshots:
        print("No published releases with registry.json assets were found", file=sys.stderr)
        return 1

    registries = []
    total_snapshots = len(snapshots)
    for index, snapshot in enumerate(snapshots, start=1):
        if index == 1 or index == total_snapshots or index % 25 == 0:
            print(
                f"Fetching snapshot {index}/{total_snapshots}: {snapshot.tag_name}",
                file=sys.stderr,
            )
        registries.append(fetch_registry_snapshot(snapshot))

    archive = build_archive_from_snapshots(registries)
    write_archive(args.output, archive)

    total_versions = sum(len(agent["versions"]) for agent in archive["agents"])
    print(
        f"Wrote {args.output} with {len(archive['agents'])} agents and "
        f"{total_versions} archived versions",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except urllib.error.URLError as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
