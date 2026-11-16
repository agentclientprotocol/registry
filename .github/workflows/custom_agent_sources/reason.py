"""Reason publishes its CLI on reasonmachines.com, not GitHub Releases.

The manifest names the current stable release; SHA256SUMS beside its archives
lists every file of that release.
"""

import re

from common import LatestRelease, ResolvedAsset, UpdateError
from github_api import make_request
from registry_utils import version_tuple

MANIFEST_URL = "https://reasonmachines.com/api/cli-manifest"
RELEASES_URL = "https://reasonmachines.com/cli/releases/download"

_PLATFORM_TARGETS = {
    "darwin-aarch64": "darwin-arm64",
    "darwin-x86_64": "darwin-x64",
    "linux-aarch64": "linux-arm64",
    "linux-x86_64": "linux-x64",
    "windows-aarch64": "win32-arm64",
    "windows-x86_64": "win32-x64",
}


def archive_name(platform: str, version: str) -> str:
    return f"reason-machines-cli-{_PLATFORM_TARGETS[platform]}-{version}.tgz"


def get_stable_release(agent_data: dict) -> tuple[LatestRelease | None, UpdateError | None]:
    agent_id = agent_data.get("id", "reason")
    manifest = make_request(MANIFEST_URL)
    if not isinstance(manifest, dict):
        return None, UpdateError(agent_id, "Could not fetch the Reason CLI manifest")

    version = manifest.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        return None, UpdateError(agent_id, "Reason CLI manifest has no stable version")
    current = version_tuple(agent_data.get("version", "0.0.0"))
    latest = version_tuple(version)
    if latest[0] != current[0] or latest < current:
        return None, UpdateError(
            agent_id, f"Reason CLI version {version} is not a newer {current[0]}.x release"
        )

    base_url = f"{RELEASES_URL}/cli-v{version}"
    if manifest.get("downloadBaseUrl") != base_url:
        return None, UpdateError(agent_id, "Unexpected Reason CLI download location")
    sums = make_request(f"{base_url}/SHA256SUMS")
    if not isinstance(sums, str):
        return None, UpdateError(agent_id, f"Could not fetch Reason CLI {version} checksums")
    digests = {}
    for line in sums.splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(\S+)", line.strip())
        if match:
            digests[match.group(2)] = match.group(1).lower()

    assets = {}
    for platform in agent_data.get("distribution", {}).get("binary", {}):
        if platform not in _PLATFORM_TARGETS:
            return None, UpdateError(agent_id, f"Unknown Reason CLI platform {platform}")
        name = archive_name(platform, version)
        if name not in digests:
            return None, UpdateError(agent_id, f"Reason CLI {version} lacks {platform}")
        assets[platform] = ResolvedAsset(f"{base_url}/{name}", digests[name])

    if not assets:
        return None, UpdateError(agent_id, "Reason entry has no binary platforms")
    return LatestRelease(
        version=version,
        distribution_type="binary",
        source_url=MANIFEST_URL,
        repository=agent_data.get("repository", ""),
        resolved_assets=assets,
    ), None
