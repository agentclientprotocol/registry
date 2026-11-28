"""Ensure the binary updater cannot publish partial, foreign or mismatched Muse Code releases."""

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

import strict_http
from custom_agent_sources import muse_code
from update_versions import apply_update, check_agent_version

BUILD = "1.4.25-R9200.1"
SIZE = 400_000_000


def download_url(build: str, file_name: str) -> str:
    return f"{muse_code.DOWNLOAD_PREFIX}{build}&file={file_name}"


@pytest.fixture
def entry():
    return {
        "id": "muse-code",
        "version": "1.4.24",
        "distribution": {
            "binary": {
                platform: {
                    "archive": "old-url",
                    "sha256": "old-digest",
                    "cmd": "./muse.exe" if platform.startswith("windows") else "./muse",
                    "args": ["acp"],
                    "env": {"MUSE_EXPERIMENTAL_ACP": "on"},
                }
                for platform in muse_code.PLATFORMS
            }
        },
    }


def make_channel(build):
    return {
        "channel": "muse-stable",
        "version": build,
        "manifest_url": download_url(build, "manifest.json"),
        "urgency": "none",
        "state": "public",
        "min_version": None,
    }


def make_manifest(build):
    return {
        "version": build,
        "checksum_algorithm": "sha256",
        "artifacts": {
            key: {"url": download_url(build, file_name), "checksum": "a" * 64, "size": SIZE}
            for key, file_name in muse_code.PLATFORMS.values()
        }
        | {"universal_macos_pkg": {"url": download_url(build, "muse.pkg"), "size": 1}},
    }


@pytest.fixture
def channel():
    return make_channel(BUILD)


@pytest.fixture
def manifest():
    return make_manifest(BUILD)


def serve(channel, manifest, head=("application/octet-stream", SIZE)):
    def fetch_json(url):
        if url == muse_code.CHANNEL_URL:
            return channel
        if url == channel.get("manifest_url"):
            return manifest
        raise muse_code._FeedError(f"HTTP 404 for {url}")

    return (
        patch.object(muse_code, "_fetch_json", side_effect=fetch_json),
        patch.object(muse_code, "_head", return_value=head),
    )


def check(entry, channel, manifest, tmp_path, **kwargs):
    path = tmp_path / "agent.json"
    path.write_text(json.dumps(entry))
    fetch, head = serve(channel, manifest, **kwargs)
    with fetch, head:
        return path, *check_agent_version(path, entry)


def test_updates_all_binary_urls_and_checksums(entry, channel, manifest, tmp_path):
    path, update, error = check(entry, channel, manifest, tmp_path)
    assert error is None
    assert update.latest_version == "1.4.25"
    assert apply_update(update)
    updated = json.loads(path.read_text())
    assert updated["version"] == "1.4.25"
    for platform, target in updated["distribution"]["binary"].items():
        assert target["archive"] == download_url(BUILD, muse_code.PLATFORMS[platform][1])
        assert target["sha256"] == "a" * 64
        assert target["cmd"] == entry["distribution"]["binary"][platform]["cmd"]
        assert target["args"] == ["acp"]
        assert target["env"] == {"MUSE_EXPERIMENTAL_ACP": "on"}


def pin(entry, build):
    entry["version"] = build.split("-")[0]
    for platform, target in entry["distribution"]["binary"].items():
        target["archive"] = download_url(build, muse_code.PLATFORMS[platform][1])


def test_current_build_reads_only_the_channel(entry, channel, manifest, tmp_path):
    pin(entry, BUILD)
    path = tmp_path / "agent.json"
    path.write_text(json.dumps(entry))
    fetch, head = serve(channel, manifest)
    with fetch as fetch_json, head as head_request:
        update, error = check_agent_version(path, entry)
    assert (update, error) == (None, None)
    fetch_json.assert_called_once_with(muse_code.CHANNEL_URL)
    head_request.assert_not_called()


def test_rebuild_of_current_version_is_reported(entry, channel, manifest, tmp_path):
    pin(entry, "1.4.25-R9100.1")
    _, update, error = check(entry, channel, manifest, tmp_path)
    assert update is None
    assert f"channel serves {BUILD}, a rebuild of 1.4.25; update by hand" in error.error


@pytest.mark.parametrize("build", ["1.4.23-R9000.1", "1.3.9-R8000.1"])
def test_follows_rollback_within_major_version(entry, tmp_path, build):
    path, update, error = check(entry, make_channel(build), make_manifest(build), tmp_path)
    assert error is None
    assert update.latest_version == build.split("-")[0]
    assert apply_update(update)
    target = json.loads(path.read_text())["distribution"]["binary"]["linux-x86_64"]
    assert target["archive"] == download_url(build, "muse-x86-linux")


def test_ignores_unregistered_manifest_artifacts(entry, channel, manifest, tmp_path):
    del entry["distribution"]["binary"]["windows-aarch64"]
    _, update, error = check(entry, channel, manifest, tmp_path)
    assert error is None
    assert set(update.resolved_assets) == set(entry["distribution"]["binary"])


def _break(fault, entry, channel, manifest):
    key, file_name = muse_code.PLATFORMS["windows-aarch64"]
    artifact = manifest["artifacts"][key]
    match fault:
        case "empty_channel":
            channel.clear()
        case "other_channel":
            channel["channel"] = "muse-beta"
        case "not_public":
            channel["state"] = "internal"
        case "bad_build":
            channel["version"] = "1.4.25"
        case "new_major":
            channel |= make_channel("2.0.0-R9300.1")
            manifest |= make_manifest("2.0.0-R9300.1")
        case "old_major":
            channel |= make_channel("0.9.0-R100.1")
            manifest |= make_manifest("0.9.0-R100.1")
        case "foreign_manifest":
            channel["manifest_url"] = "https://example.com/manifest.json"
        case "manifest_mismatch":
            manifest["version"] = "1.4.25-R9201.1"
        case "wrong_algorithm":
            manifest["checksum_algorithm"] = "md5"
        case "artifacts_not_object":
            manifest["artifacts"] = list(manifest["artifacts"].values())
        case "missing_platform":
            del manifest["artifacts"][key]
        case "swapped_platform":
            artifact["url"] = download_url(BUILD, "muse-x86-windows.exe")
        case "stale_url":
            artifact["url"] = download_url("1.4.24-R9131.1", file_name)
        case "foreign_url":
            artifact["url"] = f"https://example.com/?version={BUILD}&file={file_name}"
        case "checksum":
            artifact["checksum"] = "bad"
        case "checksum_not_string":
            artifact["checksum"] = 0xA
        case "string_size":
            artifact["size"] = str(SIZE)
        case "bool_size":
            artifact["size"] = True
        case "zero_size":
            artifact["size"] = 0
        case "negative_size":
            artifact["size"] = -SIZE
        case "unknown_platform":
            entry["distribution"]["binary"]["linux-x86_64-musl"] = {"archive": "x"}
        case "no_platforms":
            entry["distribution"]["binary"] = {}


URL_ERROR = "windows-aarch64: URL is not"
CHANNEL_ERROR = "is not the public muse-stable channel"
MANIFEST_ERROR = f"manifest for {BUILD} is malformed or names another build"
CHECKSUM_ERROR = "windows-aarch64: checksum is not 64 hex chars"
SIZE_ERROR = "windows-aarch64: size must be a positive int"


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ("empty_channel", CHANNEL_ERROR),
        ("other_channel", CHANNEL_ERROR),
        ("not_public", CHANNEL_ERROR),
        ("bad_build", "unexpected build version '1.4.25'"),
        ("new_major", "channel version 2.0.0 is not a 1.x release"),
        ("old_major", "channel version 0.9.0 is not a 1.x release"),
        ("foreign_manifest", "manifest URL is not"),
        ("manifest_mismatch", MANIFEST_ERROR),
        ("wrong_algorithm", MANIFEST_ERROR),
        ("artifacts_not_object", MANIFEST_ERROR),
        ("missing_platform", URL_ERROR),
        ("swapped_platform", URL_ERROR),
        ("stale_url", URL_ERROR),
        ("foreign_url", URL_ERROR),
        ("checksum", CHECKSUM_ERROR),
        ("checksum_not_string", CHECKSUM_ERROR),
        ("string_size", SIZE_ERROR),
        ("bool_size", SIZE_ERROR),
        ("zero_size", SIZE_ERROR),
        ("negative_size", SIZE_ERROR),
        ("unknown_platform", "no Muse Code build is known for linux-x86_64-musl"),
        ("no_platforms", "agent.json has no binary platforms"),
    ],
)
def test_rejects_unusable_feed(entry, channel, manifest, tmp_path, fault, message):
    _break(fault, entry, channel, manifest)
    _, update, error = check(entry, channel, manifest, tmp_path)
    assert update is None
    assert error.agent_id == "muse-code"
    assert message in error.error


@pytest.mark.parametrize(
    ("head", "got"),
    [
        (("text/html", SIZE), f"got text/html, {SIZE} bytes"),
        (("application/octet-stream", SIZE - 1), f"got application/octet-stream, {SIZE - 1} bytes"),
    ],
    ids=["html", "truncated"],
)
def test_rejects_binary_that_is_not_the_advertised_file(
    entry, channel, manifest, tmp_path, head, got
):
    _, update, error = check(entry, channel, manifest, tmp_path, head=head)
    assert update is None
    assert got in error.error


def test_head_failure_is_reported(entry, channel, manifest, tmp_path):
    fetch, _ = serve(channel, manifest)
    path = tmp_path / "agent.json"
    path.write_text(json.dumps(entry))
    failing_head = patch.object(
        muse_code, "_head", side_effect=muse_code._FeedError("HTTP 404 for x")
    )
    with fetch, failing_head:
        update, error = check_agent_version(path, entry)
    assert update is None
    assert "HTTP 404" in error.error


@pytest.mark.parametrize("code", [302, 410])
def test_requests_go_through_strict_http(entry, tmp_path, code):
    path = tmp_path / "agent.json"
    path.write_text(json.dumps(entry))
    failure = urllib.error.HTTPError(muse_code.CHANNEL_URL, code, "msg", {}, None)
    with patch.object(strict_http._OPENER, "open", side_effect=failure) as open_:
        update, error = check_agent_version(path, entry)
    assert update is None
    assert f"HTTP {code} for {muse_code.CHANNEL_URL}" in error.error
    assert open_.call_args.args[0].get_header("Cache-control") == "no-cache"


@pytest.mark.parametrize(
    ("body", "message"),
    [(b"<html></html>", "not JSON"), (b"[]", "expected a JSON object")],
    ids=["html", "array"],
)
def test_channel_must_be_a_json_object(entry, tmp_path, body, message):
    path = tmp_path / "agent.json"
    path.write_text(json.dumps(entry))
    with patch.object(strict_http._OPENER, "open", return_value=io.BytesIO(body)):
        update, error = check_agent_version(path, entry)
    assert update is None
    assert f"{muse_code.CHANNEL_URL}: {message}" in error.error
