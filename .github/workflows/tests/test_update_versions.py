"""Tests for update_versions.py."""

import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

from update_versions import check_agent_version, make_request


class TestMakeRequestServerErrors:
    """Test that make_request handles server errors (5xx) gracefully."""

    @patch("update_versions.urllib.request.urlopen")
    def test_502_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.github.com/repos/owner/repo/releases/latest",
            code=502,
            msg="Bad Gateway",
            hdrs={},
            fp=None,
        )
        assert make_request("https://api.github.com/repos/owner/repo/releases/latest") is None

    @patch("update_versions.urllib.request.urlopen")
    def test_503_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.github.com/repos/owner/repo/releases/latest",
            code=503,
            msg="Service Unavailable",
            hdrs={},
            fp=None,
        )
        assert make_request("https://api.github.com/repos/owner/repo/releases/latest") is None

    @patch("update_versions.urllib.request.urlopen")
    def test_500_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com/api",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=None,
        )
        assert make_request("https://example.com/api") is None

    @patch("update_versions.urllib.request.urlopen")
    def test_404_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com/api",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )
        assert make_request("https://example.com/api") is None

    @patch("update_versions.urllib.request.urlopen")
    def test_403_raises(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com/api",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None,
        )
        with pytest.raises(urllib.error.HTTPError, match="403"):
            make_request("https://example.com/api")

    @patch("update_versions.urllib.request.urlopen")
    def test_429_raises(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com/api",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=None,
        )
        with pytest.raises(urllib.error.HTTPError, match="429"):
            make_request("https://example.com/api")


class TestCheckAgentVersionNonGitHubRepo:
    """Test that non-GitHub repository URLs are skipped for binary distributions."""

    def test_non_github_repo_binary_only_is_skipped(self):
        """Binary-only agent with non-GitHub repository should be silently skipped."""
        agent_data = {
            "id": "cursor",
            "version": "0.1.0",
            "repository": "https://cursor.com/docs/cli/acp",
            "distribution": {
                "binary": {
                    "darwin-aarch64": {
                        "archive": "https://example.com/agent.tar.gz",
                        "cmd": "./agent",
                    }
                }
            },
        }
        update, error = check_agent_version(Path("cursor/agent.json"), agent_data)
        assert update is None
        assert error is None

    def test_website_only_binary_is_skipped(self):
        """Binary-only agent with website metadata but no repository should be silently skipped."""
        agent_data = {
            "id": "cursor",
            "version": "0.1.0",
            "website": "https://cursor.com/docs/cli/acp",
            "distribution": {
                "binary": {
                    "darwin-aarch64": {
                        "archive": "https://example.com/agent.tar.gz",
                        "cmd": "./agent",
                    }
                }
            },
        }
        update, error = check_agent_version(Path("cursor/agent.json"), agent_data)
        assert update is None
        assert error is None

    def test_no_repo_binary_only_is_skipped(self):
        """Binary-only agent with no repository should be silently skipped."""
        agent_data = {
            "id": "some-agent",
            "version": "1.0.0",
            "distribution": {
                "binary": {
                    "darwin-aarch64": {
                        "archive": "https://example.com/agent.tar.gz",
                        "cmd": "./agent",
                    }
                }
            },
        }
        update, error = check_agent_version(Path("some-agent/agent.json"), agent_data)
        assert update is None
        assert error is None

    @patch("update_versions.get_github_latest_release")
    def test_github_repo_binary_still_checked(self, mock_gh_release):
        """Binary agent with GitHub repository should still be checked."""
        mock_gh_release.return_value = ("2.0.0", ["asset.tar.gz"])
        agent_data = {
            "id": "some-agent",
            "version": "1.0.0",
            "repository": "https://github.com/owner/repo",
            "distribution": {
                "binary": {
                    "darwin-aarch64": {
                        "archive": "https://github.com/owner/repo/releases/download/v1.0.0/agent.tar.gz",
                        "cmd": "./agent",
                    }
                }
            },
        }
        update, error = check_agent_version(Path("some-agent/agent.json"), agent_data)
        assert error is None
        assert update is not None
        assert update.latest_version == "2.0.0"
        mock_gh_release.assert_called_once_with("https://github.com/owner/repo")
