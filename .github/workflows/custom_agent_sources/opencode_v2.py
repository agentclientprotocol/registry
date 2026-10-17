"""OpenCode V2 publishes standalone binaries outside GitHub Releases."""

import re

from common import LatestRelease, ResolvedAsset, UpdateError
from github_api import make_request

BINARY_FEED_URL = "https://opencode.ai/update/api/latest/cli/opencode"

_PLATFORM_ASSETS = {
    "darwin-aarch64": "opencode-darwin-arm64.zip",
    "darwin-x86_64": "opencode-darwin-x64.zip",
    "linux-aarch64": "opencode-linux-arm64.tar.gz",
    "linux-x86_64": "opencode-linux-x64.tar.gz",
    "windows-aarch64": "opencode-windows-arm64.zip",
    "windows-x86_64": "opencode-windows-x64.zip",
}


def get_stable_release(agent_data: dict) -> tuple[LatestRelease | None, UpdateError | None]:
    agent_id = agent_data.get("id", "opencode-v2")
    data = make_request(BINARY_FEED_URL)
    if not isinstance(data, dict):
        return None, UpdateError(agent_id, "Could not fetch OpenCode binary feed")

    version = data.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        return None, UpdateError(agent_id, "OpenCode binary feed has no stable version")
    if data.get("distribution") != "opencode" or data.get("name") != "cli":
        return None, UpdateError(agent_id, "Unexpected OpenCode binary feed distribution")

    metadata = data.get("metadata")
    files = metadata.get("files") if isinstance(metadata, dict) else None
    if not isinstance(files, dict):
        return None, UpdateError(agent_id, "OpenCode binary feed has no files")

    assets = {}
    for platform in agent_data.get("distribution", {}).get("binary", {}):
        filename = _PLATFORM_ASSETS.get(platform)
        asset = files.get(filename)
        expected_url = f"https://opencode.ai/files/bin/{version}/{filename}"
        if not isinstance(asset, dict) or asset.get("url") != expected_url:
            return None, UpdateError(agent_id, f"Missing or invalid OpenCode asset for {platform}")
        digest = asset.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            return None, UpdateError(agent_id, f"Invalid OpenCode checksum for {platform}")
        assets[platform] = ResolvedAsset(expected_url, digest)

    if not assets:
        return None, UpdateError(agent_id, "OpenCode entry has no binary platforms")
    return LatestRelease(
        version=version,
        distribution_type="binary",
        source_url=BINARY_FEED_URL,
        repository=agent_data.get("repository", ""),
        resolved_assets=assets,
    ), None
