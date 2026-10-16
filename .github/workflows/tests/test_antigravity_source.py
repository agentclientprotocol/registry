"""Tests for custom_agent_sources/antigravity.py."""

import json
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

from custom_agent_sources import antigravity
from update_versions import check_agent_version

BASE = antigravity.FEED_BASE
_FILES = {
    "darwin-aarch64": ("macos", "darwin-arm64"),
    "darwin-x86_64": ("macos", "darwin-x86_64"),
    "linux-x86_64": ("linux", "linux-x86_64"),
    "linux-aarch64": ("linux", "linux-arm64"),
    "windows-x86_64": ("windows", "windows-x86_64"),
    "windows-aarch64": ("windows", "windows-arm64"),
}

# Byte-for-byte the format Antigravity's publisher writes (sorted keys, indent 2).
EXAMPLE_LINK = """{
  "platforms": {
    "darwin-aarch64": {
      "archive": "https://dl.google.com/agy-extensions/releases/macos/agy-acp-server-1.3.0-darwin-arm64.zip",
      "sha256": "7cd97045f7b4fe81175a107cdf16f9c51484e3c78a5162cae415338bb6aa5b88",
      "size": 111456962
    },
    "darwin-x86_64": {
      "archive": "https://dl.google.com/agy-extensions/releases/macos/agy-acp-server-1.3.0-darwin-x86_64.zip",
      "sha256": "bb23956b89984bf5d354af2c3725e6c57f0cc1b7228e77a0e91c9c2bc1d47646",
      "size": 117245544
    },
    "linux-aarch64": {
      "archive": "https://dl.google.com/agy-extensions/releases/linux/agy-acp-server-1.3.0-linux-arm64.zip",
      "sha256": "500b0bc0fb858e88f4df404d4cedf80bf9298c178291e39e383d6c50b111cbdf",
      "size": 321690363
    },
    "linux-x86_64": {
      "archive": "https://dl.google.com/agy-extensions/releases/linux/agy-acp-server-1.3.0-linux-x86_64.zip",
      "sha256": "9fb60956af0a9d76220a4db91ca9ac88e2a2372ad68f985ab5fceace6b825b96",
      "size": 333727150
    },
    "windows-aarch64": {
      "archive": "https://dl.google.com/agy-extensions/releases/windows/agy-acp-server-1.3.0-windows-arm64.zip",
      "sha256": "4a0f469720e9beb9438a979f543fdbfad5022ebe0992c052c590bd78b3144ca3",
      "size": 124654803
    },
    "windows-x86_64": {
      "archive": "https://dl.google.com/agy-extensions/releases/windows/agy-acp-server-1.3.0-windows-x86_64.zip",
      "sha256": "65215e0688681fa3116e048a9eab27ef53af1bbd6f3da3f1c52bd4911d8b17f9",
      "size": 124509787
    }
  },
  "version": "1.3.0"
}
"""


def _archive(version: str, platform: str) -> str:
    os_dir, suffix = _FILES[platform]
    return f"https://dl.google.com/agy-extensions/releases/{os_dir}/agy-acp-server-{version}-{suffix}.zip"


def _link(version: str, **overrides) -> bytes:
    platforms = {
        p: {"archive": _archive(version, p), "sha256": "a" * 64, "size": 100} for p in _FILES
    }
    for platform, entry in overrides.pop("platforms", {}).items():
        if entry is None:
            platforms.pop(platform)
        else:
            platforms[platform] = entry
    return json.dumps({"version": version, "platforms": platforms, **overrides}).encode()


class FakeFeed:
    """Serves chain links, yank markers, and archive HEADs from memory."""

    def __init__(self, links: dict[str, bytes], yanked=(), heads=None, errors=None):
        self.links = links
        self.yanked = set(yanked)
        self.heads = heads or {}
        self.errors = errors or {}
        self.requests: list[str] = []

    def get(self, url: str) -> tuple[int, bytes]:
        self.requests.append(url)
        if url in self.errors:
            raise self.errors[url]
        for version, body in self.links.items():
            if url == f"{BASE}/next/{version}/acp_next.json":
                return 200, body
        for version in self.yanked:
            if url == f"{BASE}/yanked/{version}/acp_yanked.json":
                return 200, b'{"version": "%s", "reason": "test"}' % version.encode()
        return 404, b""

    def head(self, url: str) -> tuple[int, str, int]:
        self.requests.append(f"HEAD {url}")
        if url in self.errors:
            raise self.errors[url]
        return self.heads.get(url, (200, "application/zip", 100))


@pytest.fixture
def feed():
    def install(**kwargs):
        fake = FakeFeed(**kwargs)
        patchers = [
            patch("custom_agent_sources.antigravity._get", side_effect=fake.get),
            patch("custom_agent_sources.antigravity._head", side_effect=fake.head),
        ]
        for p in patchers:
            p.start()
        installed.extend(patchers)
        return fake

    installed: list = []
    yield install
    for p in installed:
        p.stop()


def _agent(version: str = "1.3.0") -> dict:
    return {"id": "antigravity-acp", "version": version}


class TestGetStableRelease:
    def test_one_hop_returns_the_linked_version(self, feed):
        feed(links={"1.3.0": _link("1.4.0")})

        release, error = antigravity.get_stable_release(_agent())

        assert error is None
        assert release.version == "1.4.0"
        assert release.distribution_type == "binary"
        assert release.source_url == f"{BASE}/next/1.3.0/acp_next.json"
        assert set(release.resolved_assets) == set(_FILES)
        assert release.resolved_assets["linux-aarch64"].archive_url == _archive(
            "1.4.0", "linux-aarch64"
        )

    def test_follows_the_chain_to_the_end(self, feed):
        fake = feed(links={"1.3.0": _link("1.4.0"), "1.4.0": _link("1.4.1")})

        release, error = antigravity.get_stable_release(_agent())

        assert error is None
        assert release.version == "1.4.1"
        assert fake.requests[:5] == [
            f"{BASE}/next/1.3.0/acp_next.json",
            f"{BASE}/yanked/1.4.0/acp_yanked.json",
            f"{BASE}/next/1.4.0/acp_next.json",
            f"{BASE}/yanked/1.4.1/acp_yanked.json",
            f"{BASE}/next/1.4.1/acp_next.json",
        ]
        assert sum(r.startswith("HEAD ") for r in fake.requests) == 6

    def test_no_link_for_current_version_means_no_update(self, feed):
        fake = feed(links={})

        assert antigravity.get_stable_release(_agent()) == (None, None)
        assert fake.requests == [f"{BASE}/next/1.3.0/acp_next.json"]

    def test_yanked_version_is_skipped(self, feed):
        feed(links={"1.3.0": _link("1.4.0"), "1.4.0": _link("1.4.1")}, yanked={"1.4.0"})

        release, error = antigravity.get_stable_release(_agent())

        assert error is None
        assert release.version == "1.4.1"

    def test_yanked_tail_falls_back_to_the_newest_good_version(self, feed):
        fake = feed(links={"1.3.0": _link("1.4.0"), "1.4.0": _link("1.4.1")}, yanked={"1.4.1"})

        release, error = antigravity.get_stable_release(_agent())

        assert error is None
        assert release.version == "1.4.0"
        assert f"HEAD {_archive('1.4.0', 'darwin-aarch64')}" in fake.requests

    def test_every_new_version_yanked_means_no_update(self, feed):
        # e.g. a maintainer rolled the registry back to 1.3.0 after yanking 1.4.0.
        fake = feed(links={"1.3.0": _link("1.4.0")}, yanked={"1.4.0"})

        assert antigravity.get_stable_release(_agent()) == (None, None)
        assert not any(r.startswith("HEAD ") for r in fake.requests)

    def test_missing_platform_is_an_error(self, feed):
        feed(links={"1.3.0": _link("1.4.0", platforms={"windows-aarch64": None})})

        release, error = antigravity.get_stable_release(_agent())

        assert release is None
        assert error.agent_id == "antigravity-acp"
        assert "expected platforms" in error.error

    def test_archive_outside_allowlist_is_an_error(self, feed):
        bad = {"archive": "https://example.com/agy.zip", "sha256": "a" * 64, "size": 100}
        feed(links={"1.3.0": _link("1.4.0", platforms={"linux-x86_64": bad})})

        release, error = antigravity.get_stable_release(_agent())

        assert release is None
        assert "allowlist" in error.error

    @pytest.mark.parametrize(
        "entry",
        [
            {"sha256": "ABC"},
            {"sha256": "a" * 63},
            {"size": 0},
            {"size": "100"},
            {"size": True},
        ],
    )
    def test_bad_asset_fields_are_errors(self, feed, entry):
        asset = {"archive": _archive("1.4.0", "linux-x86_64"), "sha256": "a" * 64, "size": 100}
        feed(links={"1.3.0": _link("1.4.0", platforms={"linux-x86_64": {**asset, **entry}})})

        release, error = antigravity.get_stable_release(_agent())

        assert release is None
        assert error is not None

    def test_version_going_down_is_an_error(self, feed):
        feed(links={"1.3.0": _link("1.2.9")})

        release, error = antigravity.get_stable_release(_agent())

        assert release is None
        assert "not newer" in error.error

    def test_malformed_json_is_an_error(self, feed):
        feed(links={"1.3.0": b"<html>oops</html>"})

        release, error = antigravity.get_stable_release(_agent())

        assert release is None
        assert "malformed" in error.error

    def test_chain_longer_than_cap_is_an_error(self, feed, monkeypatch):
        monkeypatch.setattr(antigravity, "MAX_HOPS", 2)
        feed(links={"1.3.0": _link("1.4.0"), "1.4.0": _link("1.4.1"), "1.4.1": _link("1.4.2")})

        release, error = antigravity.get_stable_release(_agent())

        assert release is None
        assert "longer than 2" in error.error

    @pytest.mark.parametrize(
        "head",
        [
            (404, "", -1),
            (200, "text/html", 100),
            (200, "application/zip", 99),
        ],
    )
    def test_archive_that_is_not_the_advertised_zip_is_an_error(self, feed, head):
        url = _archive("1.4.0", "windows-x86_64")
        feed(links={"1.3.0": _link("1.4.0")}, heads={url: head})

        release, error = antigravity.get_stable_release(_agent())

        assert release is None
        assert "windows-x86_64" in error.error

    def test_transient_failure_skips_without_error(self, feed, capsys):
        url = f"{BASE}/next/1.3.0/acp_next.json"
        feed(links={}, errors={url: antigravity._Transient(f"HTTP 503 for {url}")})

        assert antigravity.get_stable_release(_agent()) == (None, None)
        assert "::warning::antigravity-acp" in capsys.readouterr().err

    def test_transient_failure_on_archive_head_skips_without_error(self, feed):
        url = _archive("1.4.0", "darwin-x86_64")
        feed(links={"1.3.0": _link("1.4.0")}, errors={url: antigravity._Transient("timeout")})

        assert antigravity.get_stable_release(_agent()) == (None, None)


class TestHttpStatusMapping:
    def _open_raising(self, exc):
        return patch.object(antigravity._OPENER, "open", side_effect=exc)

    def _http_error(self, code: int) -> urllib.error.HTTPError:
        return urllib.error.HTTPError("https://dl.google.com/x", code, "msg", {}, None)

    def test_404_is_end_of_chain(self):
        with self._open_raising(self._http_error(404)):
            assert antigravity._get(f"{BASE}/next/1.3.0/acp_next.json") == (404, b"")

    @pytest.mark.parametrize("code", [500, 502, 503])
    def test_5xx_is_transient(self, code):
        with self._open_raising(self._http_error(code)), pytest.raises(antigravity._Transient):
            antigravity._get(f"{BASE}/next/1.3.0/acp_next.json")

    @pytest.mark.parametrize("code", [301, 302, 307, 403])
    def test_redirects_and_other_4xx_are_bad_feed(self, code):
        with self._open_raising(self._http_error(code)), pytest.raises(antigravity._BadFeed):
            antigravity._get(f"{BASE}/next/1.3.0/acp_next.json")

    def test_network_error_is_transient(self):
        with (
            self._open_raising(urllib.error.URLError("refused")),
            pytest.raises(antigravity._Transient),
        ):
            antigravity._get(f"{BASE}/next/1.3.0/acp_next.json")

    def test_requests_bypass_caches(self):
        with self._open_raising(self._http_error(404)) as open_:
            antigravity._get(f"{BASE}/next/1.3.0/acp_next.json")
        request = open_.call_args.args[0]
        assert "?r=" in request.full_url
        assert request.get_header("Cache-control") == "no-cache"


class TestExampleLink:
    def test_publisher_format_parses(self):
        hop = antigravity._parse_link("0.0.1", EXAMPLE_LINK.encode(), "url")

        assert hop.version == "1.3.0"
        assert hop.sizes["darwin-aarch64"] == 111456962
        assert hop.assets["linux-aarch64"].archive_url.endswith("-linux-arm64.zip")


class TestRegistration:
    def test_update_versions_uses_the_plugin(self, feed):
        feed(links={"1.3.0": _link("1.4.0")})
        agent_data = {
            "id": "antigravity-acp",
            "version": "1.3.0",
            "distribution": {"binary": {p: {"archive": "x", "cmd": "./a"} for p in _FILES}},
        }

        update, error = check_agent_version(Path("antigravity-acp/agent.json"), agent_data)

        assert error is None
        assert update.latest_version == "1.4.0"
        assert update.resolved_assets["darwin-aarch64"].sha256 == "a" * 64
