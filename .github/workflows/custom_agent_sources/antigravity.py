"""Google Antigravity's stable channel.

Each promoted release is announced by one write-once link file on
dl.google.com: `next/<from>/acp_next.json` names the version promoted after
`<from>` and its per-platform archives. Starting from the registry's current
version, follow links until a 404. A version with a `yanked/<v>/acp_yanked.json`
marker is skipped; the newest version reached that isn't yanked wins.

    {"version": "1.4.0",
     "platforms": {"darwin-aarch64": {"archive": "https://dl.google.com/...",
                                      "sha256": "...", "size": 111456962}, ...}}

Link files never change once published, so a cached copy is always correct, and
dl.google.com sends 404s without caching headers, so a new link is seen on the
next run.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import NamedTuple

from common import LatestRelease, ResolvedAsset, UpdateError
from registry_utils import version_tuple

AGENT_ID = "antigravity-acp"
FEED_BASE = "https://dl.google.com/agy-extensions/releases/acp/feed/v1"
ARCHIVE_PREFIXES = tuple(
    f"https://dl.google.com/agy-extensions/releases/{os_dir}/"
    for os_dir in ("macos", "linux", "windows")
)
PLATFORMS = frozenset(
    {
        "darwin-aarch64",
        "darwin-x86_64",
        "linux-x86_64",
        "linux-aarch64",
        "windows-x86_64",
        "windows-aarch64",
    }
)
MAX_HOPS = 50
_SHA256 = re.compile(r"[0-9a-f]{64}")


class _Transient(Exception):
    """dl.google.com is unreachable or erroring; try again next run."""


class _BadFeed(Exception):
    """The feed itself is wrong; a person needs to look."""


class _Hop(NamedTuple):
    version: str
    assets: dict[str, ResolvedAsset]
    sizes: dict[str, int]
    link_url: str
    yanked: bool


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # A redirect could lead outside the allowlist, so surface 3xx as errors.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)
_request_count = 0


def _open(url: str, method: str):
    """Sends a cache-busting request; returns None on 404."""
    global _request_count
    _request_count += 1
    busted = f"{url}?r={os.environ.get('GITHUB_RUN_ID', 'local')}-{_request_count}"
    req = urllib.request.Request(
        busted,
        method=method,
        headers={
            "User-Agent": "ACP-Registry-Version-Checker/1.0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    try:
        return _OPENER.open(req, timeout=30)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if e.code >= 500:
            raise _Transient(f"HTTP {e.code} for {url}") from e
        raise _BadFeed(f"HTTP {e.code} for {url}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise _Transient(f"{url}: {e}") from e


def _get(url: str) -> tuple[int, bytes]:
    """Returns (200, body) or (404, b"")."""
    response = _open(url, "GET")
    if response is None:
        return 404, b""
    with response:
        return response.status, response.read()


def _head(url: str) -> tuple[int, str, int]:
    """Returns (status, content type, content length); status 404 if missing."""
    response = _open(url, "HEAD")
    if response is None:
        return 404, "", -1
    with response:
        length = response.headers.get("Content-Length", "")
        return (
            response.status,
            response.headers.get_content_type(),
            int(length) if length.isdigit() else -1,
        )


def _parse_link(from_version: str, body: bytes, link_url: str) -> _Hop:
    try:
        data = json.loads(body)
        version = data["version"]
        platforms = data["platforms"]
        if version_tuple(version) <= version_tuple(from_version):
            raise _BadFeed(f"next/{from_version} names {version}, which is not newer")
    except (ValueError, KeyError, TypeError) as e:
        raise _BadFeed(f"next/{from_version}: malformed link: {e}") from e
    if not isinstance(platforms, dict) or set(platforms) != PLATFORMS:
        raise _BadFeed(f"next/{from_version}: expected platforms {sorted(PLATFORMS)}")
    assets: dict[str, ResolvedAsset] = {}
    sizes: dict[str, int] = {}
    for platform, entry in platforms.items():
        entry = entry if isinstance(entry, dict) else {}
        archive, sha256, size = entry.get("archive"), entry.get("sha256"), entry.get("size")
        if not isinstance(archive, str) or not archive.startswith(ARCHIVE_PREFIXES):
            raise _BadFeed(f"next/{from_version}: {platform} archive outside allowlist")
        if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
            raise _BadFeed(f"next/{from_version}: {platform} sha256 is not 64 hex chars")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise _BadFeed(f"next/{from_version}: {platform} size must be a positive int")
        assets[platform] = ResolvedAsset(archive_url=archive, sha256=sha256)
        sizes[platform] = size
    return _Hop(version, assets, sizes, link_url, yanked=False)


def _walk(start: str) -> list[_Hop]:
    """Follows links from `start` until a 404, noting yank markers."""
    hops: list[_Hop] = []
    version = start
    for _ in range(MAX_HOPS):
        link_url = f"{FEED_BASE}/next/{version}/acp_next.json"
        status, body = _get(link_url)
        if status == 404:
            return hops
        hop = _parse_link(version, body, link_url)
        yank_status, _ = _get(f"{FEED_BASE}/yanked/{hop.version}/acp_yanked.json")
        hops.append(hop._replace(yanked=yank_status == 200))
        version = hop.version
    raise _BadFeed(f"chain longer than {MAX_HOPS} links from {start}")


def _check_archives(hop: _Hop) -> None:
    """Confirms each archive is a zip of the advertised size, not an error page."""
    for platform, asset in sorted(hop.assets.items()):
        status, content_type, length = _head(asset.archive_url)
        if status != 200:
            raise _BadFeed(f"{hop.version} {platform}: HTTP {status} for {asset.archive_url}")
        if content_type != "application/zip" or length != hop.sizes[platform]:
            raise _BadFeed(
                f"{hop.version} {platform}: got {content_type}, {length} bytes; "
                f"expected application/zip, {hop.sizes[platform]} bytes"
            )


def get_stable_release(agent_data: dict) -> tuple[LatestRelease | None, UpdateError | None]:
    """Returns the newest promoted, non-yanked release after the registry's version."""
    try:
        hops = _walk(agent_data.get("version", ""))
        candidates = [hop for hop in hops if not hop.yanked]
        if not candidates:
            return None, None
        newest = candidates[-1]
        _check_archives(newest)
    except _Transient as e:
        # Raising here would block every agent's commit this run; skip instead.
        print(f"::warning::{AGENT_ID}: feed unavailable, skipping this run: {e}", file=sys.stderr)
        return None, None
    except _BadFeed as e:
        return None, UpdateError(AGENT_ID, f"feed: {e}")

    return LatestRelease(
        version=newest.version,
        distribution_type="binary",
        source_url=newest.link_url,
        repository="",
        resolved_assets=newest.assets,
    ), None
