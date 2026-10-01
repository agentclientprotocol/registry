"""Junie's preview (nightly) channel.

Junie's stable channel is checked the normal way (GitHub Releases). Its
preview channel instead publishes nightly binaries by appending one line per
platform to a growing `.jsonl` file. Each record looks like:

    {"version": "3531.1", "platform": "windows-aarch64",
     "downloadUrl": "https://github.com/JetBrains/junie/releases/download/...",
     "sha256": "...", "size": 367085144}
"""

from common import LatestRelease, ResolvedAsset, UpdateError
from jsonl_feed import fetch_jsonl_tail
from registry_utils import normalize_release_version, version_tuple

NIGHTLY_JSONL_URL = (
    "https://raw.githubusercontent.com/JetBrains/junie/refs/heads/main/update-info-nightly.jsonl"
)

# Nightly binaries are released from a different repo than agent.json's
# `repository` field (the stable channel's release repo).
JUNIE_REPOSITORY = "https://github.com/JetBrains/junie"

# One line per platform per version (6 platforms currently). Fetch a generous
# multiple so an in-progress upload can't split the newest version across the
# tail-window boundary.
TAIL_LINES = 60

# JSONL platform name -> registry platform key (agent.schema.json's
# binaryDistribution property names).
_PLATFORM_MAP = {
    "windows-aarch64": "windows-aarch64",
    "windows-amd64": "windows-x86_64",
    "linux-aarch64": "linux-aarch64",
    "linux-amd64": "linux-x86_64",
    "macos-aarch64": "darwin-aarch64",
    "macos-amd64": "darwin-x86_64",
}


def get_preview_release(agent_data: dict) -> tuple[LatestRelease | None, UpdateError | None]:
    """Return the newest nightly release with a complete set of platform assets."""
    agent_id = agent_data.get("id", "junie")
    records = fetch_jsonl_tail(NIGHTLY_JSONL_URL, TAIL_LINES)
    if not records:
        return None, UpdateError(agent_id, f"Could not fetch nightly feed {NIGHTLY_JSONL_URL}")

    # Only count a version as available once every platform the agent ships
    # has an uploaded asset -- an in-progress upload can appear partially.
    required_platforms = set(agent_data.get("distribution", {}).get("binary", {}))

    by_version: dict[str, dict[str, dict]] = {}
    for record in records:
        version = record.get("version")
        platform = _PLATFORM_MAP.get(record.get("platform", ""))
        if not version or not platform:
            continue
        by_version.setdefault(version, {})[platform] = record

    complete_versions = [
        version
        for version, platforms in by_version.items()
        if required_platforms <= platforms.keys()
    ]
    if not complete_versions:
        return None, UpdateError(
            agent_id, "No nightly release with a complete platform set in the fetched tail"
        )

    latest = max(complete_versions, key=version_tuple)
    resolved_assets = {
        platform: ResolvedAsset(archive_url=record["downloadUrl"], sha256=record["sha256"])
        for platform, record in by_version[latest].items()
    }

    return LatestRelease(
        version=normalize_release_version(latest) or latest,
        distribution_type="binary",
        source_url=NIGHTLY_JSONL_URL,
        repository=JUNIE_REPOSITORY,
        resolved_assets=resolved_assets,
    ), None
