"""Tests for custom_agent_sources/junie.py."""

from unittest.mock import patch

from custom_agent_sources import junie


def _record(version: str, platform: str, url: str = "", sha256: str = "abc") -> dict:
    return {
        "version": version,
        "platform": platform,
        "downloadUrl": url or f"https://github.com/JetBrains/junie/releases/download/{version}/a",
        "sha256": sha256,
        "size": 1,
    }


def _agent_data(platforms: list[str]) -> dict:
    return {
        "id": "junie",
        "distribution": {"binary": {platform: {"cmd": "./junie"} for platform in platforms}},
    }


class TestGetPreviewRelease:
    @patch("custom_agent_sources.junie.fetch_jsonl_tail")
    def test_picks_highest_complete_version(self, mock_fetch):
        mock_fetch.return_value = [
            _record("3531.1", "windows-amd64"),
            _record("3531.1", "macos-amd64"),
            _record("3534.1", "windows-amd64"),
            _record("3534.1", "macos-amd64"),
        ]
        agent_data = _agent_data(["windows-x86_64", "darwin-x86_64"])

        release, error = junie.get_preview_release(agent_data)

        assert error is None
        assert release is not None
        assert release.version == "3534.1.0"
        assert release.distribution_type == "binary"
        assert set(release.resolved_assets) == {"windows-x86_64", "darwin-x86_64"}

    @patch("custom_agent_sources.junie.fetch_jsonl_tail")
    def test_ignores_incomplete_version_still_uploading(self, mock_fetch):
        mock_fetch.return_value = [
            _record("3531.1", "windows-amd64"),
            _record("3531.1", "macos-amd64"),
            # 3534.1 only has one of the two required platforms so far.
            _record("3534.1", "windows-amd64"),
        ]
        agent_data = _agent_data(["windows-x86_64", "darwin-x86_64"])

        release, error = junie.get_preview_release(agent_data)

        assert error is None
        assert release is not None
        assert release.version == "3531.1.0"

    @patch("custom_agent_sources.junie.fetch_jsonl_tail")
    def test_maps_platform_names_to_registry_keys(self, mock_fetch):
        mock_fetch.return_value = [
            _record("3531.1", "linux-aarch64"),
        ]
        agent_data = _agent_data(["linux-aarch64"])

        release, error = junie.get_preview_release(agent_data)

        assert error is None
        assert release is not None
        assert set(release.resolved_assets) == {"linux-aarch64"}

    @patch("custom_agent_sources.junie.fetch_jsonl_tail")
    def test_unknown_platform_names_are_skipped(self, mock_fetch):
        mock_fetch.return_value = [
            _record("3531.1", "some-unknown-platform"),
            _record("3531.1", "windows-amd64"),
        ]
        agent_data = _agent_data(["windows-x86_64"])

        release, error = junie.get_preview_release(agent_data)

        assert error is None
        assert release is not None
        assert set(release.resolved_assets) == {"windows-x86_64"}

    @patch("custom_agent_sources.junie.fetch_jsonl_tail", return_value=[])
    def test_error_when_feed_fetch_fails(self, _mock_fetch):
        release, error = junie.get_preview_release(_agent_data(["windows-x86_64"]))

        assert release is None
        assert error is not None
        assert error.agent_id == "junie"

    @patch("custom_agent_sources.junie.fetch_jsonl_tail")
    def test_error_when_no_version_has_a_complete_platform_set(self, mock_fetch):
        mock_fetch.return_value = [_record("3531.1", "windows-amd64")]
        agent_data = _agent_data(["windows-x86_64", "darwin-x86_64"])

        release, error = junie.get_preview_release(agent_data)

        assert release is None
        assert error is not None
