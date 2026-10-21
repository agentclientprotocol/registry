"""GitHub API helpers, plus the shared HTTP fetch primitive (`make_request`)
also used for npm/PyPI lookups. Kept out of update_versions.py so other
modules can import it without an import cycle.
"""

import json
import os
import re
import urllib.error
import urllib.request

from registry_utils import is_prerelease, normalize_release_version


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


def is_github_repo(repo_url: str) -> bool:
    return "github.com" in repo_url


def _github_owner_repo(repo_url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from a GitHub repository URL, stripping any `.git`."""
    match = re.search(r"github\.com/([^/]+)/([^/]+)", repo_url)
    if not match:
        return None
    owner, repo = match.groups()
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def _parse_release_digests(data: dict) -> dict[str, str]:
    """Extract {asset_name: hex_sha256} from a GitHub release payload."""
    digests: dict[str, str] = {}
    for a in data.get("assets", []):
        if not isinstance(a, dict):
            continue
        name = a.get("name")
        digest = a.get("digest", "")
        if name and isinstance(digest, str) and digest.startswith("sha256:"):
            digests[name] = digest.removeprefix("sha256:")
    return digests


def get_github_latest_version(repo_url: str) -> str | None:
    parsed = _github_owner_repo(repo_url)
    if not parsed:
        return None
    owner, repo = parsed
    data = make_request(f"https://api.github.com/repos/{owner}/{repo}/releases/latest")
    if isinstance(data, dict):
        tag = data.get("tag_name", "")
        return normalize_release_version(tag.lstrip("v") if tag else None)
    return None


def get_github_release_digests(repo_url: str, version: str) -> dict[str, str]:
    """Return {asset_filename: hex_sha256} for the release tagged `version`."""
    parsed = _github_owner_repo(repo_url)
    if not parsed:
        return {}
    owner, repo = parsed
    # Try `v{version}` (common tag convention) then bare `{version}`.
    for tag in (f"v{version}", version):
        data = make_request(f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}")
        if isinstance(data, dict):
            return _parse_release_digests(data)
    return {}


def get_github_release_versions(repo_url: str) -> set[str] | None:
    """Get stable GitHub release versions published for a repository."""
    parsed = _github_owner_repo(repo_url)
    if not parsed:
        return None
    owner, repo = parsed

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

    latest = get_github_latest_version(repo_url)
    if latest:
        return {latest}

    return None
