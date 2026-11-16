"""Ensure the Reason updater reads reasonmachines.com and never publishes a partial release."""

import json
from unittest.mock import patch

import pytest

from custom_agent_sources import reason
from update_versions import apply_update, check_agent_version

BASE = "https://reasonmachines.com/cli/releases/download"


@pytest.fixture
def entry():
    return {
        "id": "reason",
        "version": "0.2.678",
        "distribution": {
            "binary": {
                platform: {
                    "archive": f"{BASE}/cli-v0.2.678/{reason.archive_name(platform, '0.2.678')}",
                    "sha256": "0" * 64,
                    "cmd": "./package/bin/reason",
                    "args": ["acp"],
                }
                for platform in reason._PLATFORM_TARGETS
            }
        },
    }


def release(version="0.2.679"):
    manifest = {
        "version": version,
        "tag": f"cli-v{version}",
        "downloadBaseUrl": f"{BASE}/cli-v{version}",
        "checksumsUrl": f"{BASE}/cli-v{version}/SHA256SUMS",
    }
    sums = "".join(
        f"{'a' * 64}  {reason.archive_name(platform, version)}\n"
        for platform in reason._PLATFORM_TARGETS
    )
    sums += f"{'b' * 64}  reason-machines-cli-linux-x64-musl-{version}.tgz\n"
    return manifest, sums


def serve(manifest, sums):
    def fake(url, headers=None):
        if url == reason.MANIFEST_URL:
            return manifest
        if url == f"{BASE}/cli-v{manifest['version']}/SHA256SUMS":
            return sums
        return None

    return fake


def test_updates_all_binary_urls_and_checksums(entry, tmp_path):
    path = tmp_path / "agent.json"
    path.write_text(json.dumps(entry))
    with patch.object(reason, "make_request", side_effect=serve(*release())):
        update, error = check_agent_version(path, entry)
    assert error is None
    assert update.latest_version == "0.2.679"
    assert apply_update(update)
    updated = json.loads(path.read_text())
    assert updated["version"] == "0.2.679"
    for platform, target in updated["distribution"]["binary"].items():
        name = reason.archive_name(platform, "0.2.679")
        assert target["archive"] == f"{BASE}/cli-v0.2.679/{name}"
        assert target["sha256"] == "a" * 64
        assert target["args"] == ["acp"]


@pytest.mark.parametrize(
    "fault", ["missing_platform", "no_checksums", "moved", "prerelease", "older", "unavailable"]
)
def test_rejects_unusable_release(entry, fault):
    manifest, sums = release()
    if fault == "missing_platform":
        sums = sums.replace(reason.archive_name("windows-aarch64", "0.2.679"), "other.tgz")
    elif fault == "no_checksums":
        sums = None
    elif fault == "moved":
        manifest["downloadBaseUrl"] = "https://example.com/cli-v0.2.679"
    elif fault == "prerelease":
        manifest["version"] = "0.2.679-beta.1"
    elif fault == "older":
        manifest, sums = release("0.2.677")
    else:
        manifest = None
    fake = serve(manifest, sums) if manifest else (lambda url, headers=None: None)
    with patch.object(reason, "make_request", side_effect=fake):
        found, error = reason.get_stable_release(entry)
    assert found is None
    assert error is not None


def test_current_version_is_up_to_date(entry, tmp_path):
    with patch.object(reason, "make_request", side_effect=serve(*release("0.2.678"))):
        update, error = check_agent_version(tmp_path / "agent.json", entry)
    assert update is None
    assert error is None


def test_registry_entry_matches_source():
    from pathlib import Path

    entry_path = Path(__file__).resolve().parents[3] / "reason" / "agent.json"
    data = json.loads(entry_path.read_text())
    version = data["version"]
    for platform, target in data["distribution"]["binary"].items():
        name = reason.archive_name(platform, version)
        assert target["archive"] == f"{BASE}/cli-v{version}/{name}"
