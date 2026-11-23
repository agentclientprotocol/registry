"""Keep the V1 `opencode` entry on 1.x while V2 shares the repository's releases."""

import json
from unittest.mock import patch

import pytest

from custom_agent_sources import opencode
from update_versions import apply_update, check_agent_version

PLATFORMS = {
    "darwin-aarch64": "opencode-darwin-arm64.zip",
    "linux-x86_64": "opencode-linux-x64.tar.gz",
}


@pytest.fixture
def entry():
    return {
        "id": "opencode",
        "version": "1.19.4",
        "repository": "https://github.com/anomalyco/opencode",
        "distribution": {
            "binary": {
                platform: {
                    "archive": f"https://github.com/anomalyco/opencode/releases/download/v1.19.4/{name}",
                    "sha256": "old-digest",
                    "cmd": "./opencode",
                    "args": ["acp"],
                }
                for platform, name in PLATFORMS.items()
            }
        },
    }


def test_updates_to_newest_1x_release_ignoring_2x(entry, tmp_path):
    path = tmp_path / "agent.json"
    path.write_text(json.dumps(entry))
    with (
        patch.object(
            opencode,
            "get_github_release_versions",
            return_value={"1.19.4", "1.19.5", "2.1.4", "2.2.0"},
        ),
        patch(
            "update_versions.get_github_release_digests",
            return_value={name: "b" * 64 for name in PLATFORMS.values()},
        ) as digests,
    ):
        update, error = check_agent_version(path, entry)
        assert error is None
        assert update.latest_version == "1.19.5"
        assert apply_update(update)
    digests.assert_called_once_with(entry["repository"], "1.19.5")
    updated = json.loads(path.read_text())
    assert updated["version"] == "1.19.5"
    for platform, target in updated["distribution"]["binary"].items():
        assert target["archive"] == (
            f"https://github.com/anomalyco/opencode/releases/download/v1.19.5/{PLATFORMS[platform]}"
        )
        assert target["sha256"] == "b" * 64
        assert target["args"] == ["acp"]


def test_newer_2x_release_alone_is_not_an_update(entry, tmp_path):
    with patch.object(opencode, "get_github_release_versions", return_value={"1.19.4", "2.2.0"}):
        update, error = check_agent_version(tmp_path / "agent.json", entry)
    assert update is None
    assert error is None


@pytest.mark.parametrize(
    ("versions", "message"),
    [
        (None, "Could not fetch GitHub releases for https://github.com/anomalyco/opencode"),
        ({"2.1.4"}, "No 1.x GitHub release found"),
        ({"1.19.3", "2.1.4"}, "Newest 1.x GitHub release 1.19.3 is older than the entry"),
    ],
)
def test_reports_unusable_releases(entry, versions, message):
    with patch.object(opencode, "get_github_release_versions", return_value=versions):
        release, error = opencode.get_stable_release(entry)
    assert release is None
    assert error.error == message
