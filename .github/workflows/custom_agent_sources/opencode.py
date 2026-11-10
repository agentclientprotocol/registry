"""OpenCode V1 stays on 1.x GitHub Releases.

V2 tags are published to the same repository without V1 archives, so the
standard highest-release rule would move this entry to 2.x. V2 is listed
separately as `opencode-v2`.
"""

from common import LatestRelease, UpdateError
from github_api import get_github_release_versions
from registry_utils import is_prerelease, version_tuple


def get_stable_release(agent_data: dict) -> tuple[LatestRelease | None, UpdateError | None]:
    agent_id = agent_data.get("id", "opencode")
    repository = agent_data.get("repository", "")
    versions = get_github_release_versions(repository)
    if not versions:
        return None, UpdateError(agent_id, f"Could not fetch GitHub releases for {repository}")

    current = version_tuple(agent_data.get("version", "0.0.0"))
    candidates = [
        version
        for version in versions
        if not is_prerelease(version) and version_tuple(version)[0] == current[0]
    ]
    if not candidates:
        return None, UpdateError(agent_id, f"No {current[0]}.x GitHub release found")

    latest = max(candidates, key=version_tuple)
    if version_tuple(latest) < current:
        return None, UpdateError(
            agent_id, f"Newest {current[0]}.x GitHub release {latest} is older than the entry"
        )
    # No resolved assets: the standard binary path rewrites the URLs and reads the digests.
    return LatestRelease(
        version=latest,
        distribution_type="binary",
        source_url=repository,
        repository=repository,
    ), None
