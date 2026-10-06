"""Ensure the binary updater cannot publish partial or mismatched OpenCode releases."""

from unittest.mock import patch

import pytest

from custom_agent_sources import opencode_v2
from update_versions import apply_update, check_agent_version


@pytest.fixture
def entry():
    return {
        "id": "opencode-v2",
        "version": "2.0.22",
        "repository": "https://github.com/anomalyco/opencode",
        "distribution": {
            "binary": {
                platform: {"archive": "old-url", "sha256": "old-digest", "cmd": "./opencode"}
                for platform in opencode_v2._PLATFORM_ASSETS
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
                for name in opencode_v2._PLATFORM_ASSETS.values()
            }
        },
    }


def test_updates_all_binary_urls_and_checksums_without_using_github(entry, feed, tmp_path):
    import json

    path = tmp_path / "agent.json"
    path.write_text(json.dumps(entry))
    with patch.object(opencode_v2, "make_request", return_value=feed):
        update, error = check_agent_version(path, entry)
    assert error is None
    assert update.latest_version == "2.0.23"
    assert apply_update(update)
    updated = json.loads(path.read_text())
    assert updated["version"] == "2.0.23"
    for platform, target in updated["distribution"]["binary"].items():
        assert (
            target["archive"]
            == feed["metadata"]["files"][opencode_v2._PLATFORM_ASSETS[platform]]["url"]
        )
        assert target["sha256"] == "a" * 64
        assert target["cmd"] == "./opencode"


@pytest.mark.parametrize(
    "fault", ["missing_platform", "checksum", "wrong_version_url", "prerelease", "unavailable"]
)
def test_rejects_unusable_feed(entry, feed, fault):
    name = opencode_v2._PLATFORM_ASSETS["windows-aarch64"]
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
    with patch.object(opencode_v2, "make_request", return_value=feed):
        release, error = opencode_v2.get_stable_release(entry)
    assert release is None
    assert error is not None


def test_v1_keeps_github_release_source(tmp_path):
    import json
    from pathlib import Path

    entry_path = Path(__file__).resolve().parents[3] / "opencode" / "agent.json"
    v1 = json.loads(entry_path.read_text())
    with (
        patch.object(opencode_v2, "make_request") as v2_feed,
        patch(
            "update_versions.get_github_release_versions", return_value={v1["version"]}
        ) as github,
    ):
        update, error = check_agent_version(entry_path, v1)
    assert update is None
    assert error is None
    v2_feed.assert_not_called()
    github.assert_called_once_with(v1["repository"])
