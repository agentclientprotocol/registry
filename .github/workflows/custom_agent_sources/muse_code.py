"""Muse Code's stable channel: the release channel its installer reads, not GitHub Releases.

The channel names the current build (e.g. `1.4.24-R9131.1`) and its manifest of raw
binaries. A rebuild of the same `x.y.z` (new `-R` suffix) isn't picked up.
"""

import json
import re
import urllib.error
import urllib.request

from common import LatestRelease, ResolvedAsset, UpdateError
from registry_utils import version_tuple

AGENT_ID = "muse-code"
CHANNEL = "muse-stable"
CHANNEL_URL = f"https://api.meta.ai/muse-code/channels/{CHANNEL}"
DOWNLOAD_PREFIX = "https://lookaside.facebook.com/lookaside/muse/download/?channel=muse&version="

# Registry platform -> (manifest artifact key, download file name).
PLATFORMS = {
    "darwin-aarch64": ("aarch64_macos", "muse-aarch64-macos"),
    "darwin-x86_64": ("x86_macos", "muse-x86-macos"),
    "linux-aarch64": ("aarch64_linux", "muse-aarch64-linux"),
    "linux-x86_64": ("x86_linux", "muse-x86-linux"),
    "windows-aarch64": ("aarch64_windows", "muse-aarch64-windows.exe"),
    "windows-x86_64": ("x86_windows", "muse-x86-windows.exe"),
}

_BUILD = re.compile(r"(\d+\.\d+\.\d+)-R\d+(?:\.\d+)?")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class _FeedError(Exception):
    """The channel is unreachable, or the channel or manifest is wrong."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # A redirect could lead outside the allowlist, so surface 3xx as errors.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _open(url: str, method: str):
    req = urllib.request.Request(
        url,
        method=method,
        headers={"User-Agent": "ACP-Registry-Version-Checker/1.0", "Cache-Control": "no-cache"},
    )
    try:
        return _OPENER.open(req, timeout=30)
    except urllib.error.HTTPError as e:
        raise _FeedError(f"HTTP {e.code} for {url}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise _FeedError(f"{url}: {e}") from e


def _fetch_json(url: str) -> dict:
    with _open(url, "GET") as response:
        body = response.read()
    try:
        data = json.loads(body)
    except ValueError as e:
        raise _FeedError(f"{url}: not JSON") from e
    if not isinstance(data, dict):
        raise _FeedError(f"{url}: expected a JSON object")
    return data


def _head(url: str) -> tuple[str, int]:
    """Returns (content type, content length) for a 200 response."""
    with _open(url, "HEAD") as response:
        length = response.headers.get("Content-Length", "")
        return response.headers.get_content_type(), int(length) if length.isdigit() else -1


def _resolve(agent_data: dict) -> LatestRelease | None:
    channel = _fetch_json(CHANNEL_URL)
    if channel.get("channel") != CHANNEL or channel.get("state") != "public":
        raise _FeedError(f"{CHANNEL_URL} is not the public {CHANNEL} channel")

    build = channel.get("version")
    match = _BUILD.fullmatch(build) if isinstance(build, str) else None
    if not match:
        raise _FeedError(f"unexpected build version {build!r}")
    version = match.group(1)

    current = version_tuple(agent_data.get("version", "0.0.0"))
    latest = version_tuple(version)
    # Follow rollbacks within a major version, as Muse's launcher does; a new major needs review.
    if latest[0] != current[0]:
        raise _FeedError(f"channel version {version} is not a {current[0]}.x release")
    if latest == current:
        # Like Muse's own launcher, stop after the channel read when nothing changed.
        return LatestRelease(version, "binary", CHANNEL_URL, "")

    manifest_url = f"{DOWNLOAD_PREFIX}{build}&file=manifest.json"
    if channel.get("manifest_url") != manifest_url:
        raise _FeedError(f"manifest URL is not {manifest_url}")
    manifest = _fetch_json(manifest_url)
    artifacts = manifest.get("artifacts")
    if (
        manifest.get("version") != build
        or manifest.get("checksum_algorithm") != "sha256"
        or not isinstance(artifacts, dict)
    ):
        raise _FeedError(f"manifest for {build} is malformed or names another build")

    platforms = agent_data.get("distribution", {}).get("binary", {})
    if not platforms:
        raise _FeedError("agent.json has no binary platforms")
    assets: dict[str, ResolvedAsset] = {}
    for platform in platforms:
        if platform not in PLATFORMS:
            raise _FeedError(f"no Muse Code build is known for {platform}")
        key, file_name = PLATFORMS[platform]
        artifact = artifacts.get(key)
        artifact = artifact if isinstance(artifact, dict) else {}
        url, digest, size = artifact.get("url"), artifact.get("checksum"), artifact.get("size")
        expected_url = f"{DOWNLOAD_PREFIX}{build}&file={file_name}"
        if url != expected_url:
            raise _FeedError(f"{platform}: URL is not {expected_url}")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise _FeedError(f"{platform}: checksum is not 64 hex chars")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise _FeedError(f"{platform}: size must be a positive int")
        content_type, length = _head(url)
        if content_type != "application/octet-stream" or length != size:
            raise _FeedError(
                f"{platform}: got {content_type}, {length} bytes; "
                f"expected application/octet-stream, {size} bytes"
            )
        assets[platform] = ResolvedAsset(archive_url=url, sha256=digest)

    return LatestRelease(
        version=version,
        distribution_type="binary",
        source_url=manifest_url,
        repository="",
        resolved_assets=assets,
    )


def get_stable_release(agent_data: dict) -> tuple[LatestRelease | None, UpdateError | None]:
    try:
        return _resolve(agent_data), None
    except _FeedError as e:
        return None, UpdateError(agent_data.get("id", AGENT_ID), f"Muse Code channel: {e}")
