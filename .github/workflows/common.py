"""Shared data types for the version-checking pipeline.

Kept separate from update_versions.py so github_api.py and
custom_agent_sources/*.py can use these types without an import cycle.
"""

from pathlib import Path
from typing import NamedTuple

CHANNELS = ("stable", "preview")


class UpdateError(NamedTuple):
    """An agent version check that failed outright."""

    agent_id: str
    error: str


class ResolvedAsset(NamedTuple):
    """A release artifact with both its URL and digest already known."""

    archive_url: str
    sha256: str


class PublishedVersions(NamedTuple):
    """All versions published under one distribution source, and its origin."""

    versions: set[str]
    source_url: str


class LatestRelease(NamedTuple):
    """The latest release a source found, before comparison against the current version."""

    version: str
    distribution_type: str  # 'npx', 'uvx', 'binary', or combined like 'binary+npx'
    source_url: str
    repository: str
    resolved_assets: dict[str, ResolvedAsset] | None = None


class VersionUpdate(NamedTuple):
    """Represents a version update for an agent, ready to write to disk."""

    agent_id: str
    agent_path: Path
    current_version: str
    latest_version: str
    distribution_type: str
    source_url: str
    repository: str
    channel: str = "stable"
    resolved_assets: dict[str, ResolvedAsset] | None = None
