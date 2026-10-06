"""Ensure the binary updater cannot publish partial or mismatched OpenCode releases."""

from unittest.mock import patch

import pytest

from custom_agent_sources import opencode
from update_versions import apply_update, check_agent_version


@pytest.fixture
def entry():
    return {
        "id": "opencode",
        "version": "2.0.22",
        "repository": "https://github.com/anomalyco/opencode",
        "distribution": {
            "binary": {
                platform: {"archive": "old-url", "sha256": "old-digest", "cmd": "./opencode"}
                for platform in opencode._PLATFORM_ASSETS
            }
        },
    }


@pytest.fixture
def feed():
    return {
        "version": "2.0.23",
        "name": "cli",
        "distribution": "opencode",
        "metadata": {
            "files": {
                name: {
                    "url": f"https://opencode.ai/files/bin/2.0.23/{name}",
                    "sha256": "a" * 64,
                }
                for name in opencode._PLATFORM_ASSETS.values()
            }
        },
    }


def test_updates_all_binary_urls_and_checksums_without_using_github(entry, feed, tmp_path):
    import json

    path = tmp_path / "agent.json"
    path.write_text(json.dumps(entry))
    with patch.object(opencode, "make_request", return_value=feed):
        update, error = check_agent_version(path, entry)
    assert error is None
    assert update.latest_version == "2.0.23"
    assert apply_update(update)
    updated = json.loads(path.read_text())
    assert updated["version"] == "2.0.23"
    for platform, target in updated["distribution"]["binary"].items():
        assert (
            target["archive"]
            == feed["metadata"]["files"][opencode._PLATFORM_ASSETS[platform]]["url"]
        )
        assert target["sha256"] == "a" * 64
        assert target["cmd"] == "./opencode"


@pytest.mark.parametrize(
    "fault", ["missing_platform", "checksum", "wrong_version_url", "prerelease", "unavailable"]
)
def test_rejects_unusable_feed(entry, feed, fault):
    name = opencode._PLATFORM_ASSETS["windows-aarch64"]
    if fault == "missing_platform":
        del feed["metadata"]["files"][name]
    elif fault == "checksum":
        feed["metadata"]["files"][name]["sha256"] = "bad"
    elif fault == "wrong_version_url":
        feed["metadata"]["files"][name]["url"] = "https://opencode.ai/files/bin/2.0.22/old.zip"
    elif fault == "prerelease":
        feed["version"] = "2.0.24-preview.1"
    else:
        feed = None
    with patch.object(opencode, "make_request", return_value=feed):
        release, error = opencode.get_stable_release(entry)
    assert release is None
    assert error is not None
