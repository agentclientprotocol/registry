"""Tests for update_versions.py."""

import json
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

from update_versions import (
    VersionUpdate,
    apply_update,
    check_agent_version,
    is_prerelease,
    make_request,
)


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


class TestPrereleaseDetection:
    """Test filtering of non-stable package versions."""

    def test_rc_suffix_is_treated_as_prerelease(self):
        assert is_prerelease("0.1.17rc0")


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

    @patch("update_versions.get_github_release_versions")
    def test_github_repo_binary_still_checked(self, mock_gh_release_versions):
        """Binary agent with GitHub repository should still be checked."""
        mock_gh_release_versions.return_value = {"2.0.0"}
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
        mock_gh_release_versions.assert_called_once_with("https://github.com/owner/repo")


class TestCheckAgentVersionMultiSourceResolution:
    """Test version resolution when multiple distribution sources disagree."""

    @patch("update_versions.get_npm_versions")
    @patch("update_versions.get_github_release_versions")
    def test_uses_latest_common_stable_version(self, mock_gh_release_versions, mock_npm_versions):
        """Pick the highest version published on every distribution source."""
        mock_npm_versions.return_value = {"7.2.0", "7.2.1", "7.2.4"}
        mock_gh_release_versions.return_value = {"7.2.0", "7.2.1"}
        agent_data = {
            "id": "kilo",
            "version": "7.2.0",
            "repository": "https://github.com/owner/repo",
            "distribution": {
                "binary": {
                    "darwin-aarch64": {
                        "archive": "https://github.com/owner/repo/releases/download/v7.2.0/agent.tar.gz",
                        "cmd": "./agent",
                    }
                },
                "npx": {
                    "package": "@owner/cli@7.2.0",
                    "args": ["acp"],
                },
            },
        }

        update, error = check_agent_version(Path("kilo/agent.json"), agent_data)

        assert error is None
        assert update is not None
        assert update.latest_version == "7.2.1"

    @patch("update_versions.get_npm_versions")
    @patch("update_versions.get_github_release_versions")
    def test_no_update_when_current_version_is_latest_common(
        self, mock_gh_release_versions, mock_npm_versions
    ):
        """Do not fail or update when sources disagree but the current version is shared."""
        mock_npm_versions.return_value = {"7.2.0", "7.2.1", "7.2.4"}
        mock_gh_release_versions.return_value = {"7.2.0", "7.2.1"}
        agent_data = {
            "id": "kilo",
            "version": "7.2.1",
            "repository": "https://github.com/owner/repo",
            "distribution": {
                "binary": {
                    "darwin-aarch64": {
                        "archive": "https://github.com/owner/repo/releases/download/v7.2.1/agent.tar.gz",
                        "cmd": "./agent",
                    }
                },
                "npx": {
                    "package": "@owner/cli@7.2.1",
                    "args": ["acp"],
                },
            },
        }

        update, error = check_agent_version(Path("kilo/agent.json"), agent_data)

        assert error is None
        assert update is None

    @patch("update_versions.get_npm_versions")
    @patch("update_versions.get_github_release_versions")
    def test_returns_error_when_sources_have_no_common_version(
        self, mock_gh_release_versions, mock_npm_versions
    ):
        """Keep the mismatch as an error when there is no shared stable version."""
        mock_npm_versions.return_value = {"7.2.4"}
        mock_gh_release_versions.return_value = {"7.2.1"}
        agent_data = {
            "id": "kilo",
            "version": "7.2.0",
            "repository": "https://github.com/owner/repo",
            "distribution": {
                "binary": {
                    "darwin-aarch64": {
                        "archive": "https://github.com/owner/repo/releases/download/v7.2.0/agent.tar.gz",
                        "cmd": "./agent",
                    }
                },
                "npx": {
                    "package": "@owner/cli@7.2.0",
                    "args": ["acp"],
                },
            },
        }

        update, error = check_agent_version(Path("kilo/agent.json"), agent_data)

        assert update is None
        assert error is not None
        assert error.error == "Version mismatch across distributions: binary=7.2.1, npx=7.2.4"


class TestApplyUpdateUrlValidation:
    """apply_update reverts and reports skipped when new URLs aren't reachable.

    Regression test for the failure mode where an upstream stops publishing one
    platform's binary at a new version (e.g. vtcode 0.105.5 dropped Windows zip),
    which previously caused the entire hourly auto-update workflow to fail.
    """

    def _write_agent(self, tmpdir: Path, agent_data: dict) -> Path:
        agent_dir = tmpdir / agent_data["id"]
        agent_dir.mkdir()
        path = agent_dir / "agent.json"
        path.write_text(json.dumps(agent_data, indent=2) + "\n")
        return path

    def _build_update(self, path: Path, agent_data: dict, new_version: str) -> VersionUpdate:
        return VersionUpdate(
            agent_id=agent_data["id"],
            agent_path=path,
            current_version=agent_data["version"],
            latest_version=new_version,
            distribution_type="binary",
            source_url="https://github.com/owner/repo",
        )

    def test_reverts_when_new_binary_url_missing(self):
        agent_data = {
            "id": "vtlike",
            "version": "0.96.14",
            "distribution": {
                "binary": {
                    "darwin-aarch64": {
                        "archive": "https://github.com/owner/repo/releases/download/0.96.14/agent-0.96.14-aarch64-apple-darwin.tar.gz",
                        "cmd": "./agent",
                    },
                    "windows-x86_64": {
                        "archive": "https://github.com/owner/repo/releases/download/0.96.14/agent-0.96.14-x86_64-pc-windows-msvc.zip",
                        "cmd": "agent.exe",
                    },
                }
            },
        }
        with tempfile.TemporaryDirectory() as d:
            tmpdir = Path(d)
            path = self._write_agent(tmpdir, agent_data)
            original = path.read_text()
            update = self._build_update(path, agent_data, "0.105.5")

            # New version's Windows zip 404s; macOS exists.
            def fake_url_exists(url, *_args, **_kwargs):
                return "windows" not in url

            with patch("registry_utils.url_exists", side_effect=fake_url_exists):
                ok, reason = apply_update(update)

            assert ok is False
            assert reason is not None
            assert "windows-x86_64" in reason
            # File must be byte-identical to its pre-update state.
            assert path.read_text() == original

    def test_succeeds_when_all_new_urls_reachable(self):
        agent_data = {
            "id": "okagent",
            "version": "1.0.0",
            "distribution": {
                "binary": {
                    "darwin-aarch64": {
                        "archive": "https://github.com/owner/repo/releases/download/1.0.0/agent-1.0.0-aarch64-apple-darwin.tar.gz",
                        "cmd": "./agent",
                    },
                }
            },
        }
        with tempfile.TemporaryDirectory() as d:
            tmpdir = Path(d)
            path = self._write_agent(tmpdir, agent_data)
            update = self._build_update(path, agent_data, "1.1.0")

            with patch("registry_utils.url_exists", return_value=True):
                ok, reason = apply_update(update)

            assert ok is True
            assert reason is None
            written = json.loads(path.read_text())
            assert written["version"] == "1.1.0"
            assert (
                written["distribution"]["binary"]["darwin-aarch64"]["archive"]
                == "https://github.com/owner/repo/releases/download/1.1.0/agent-1.1.0-aarch64-apple-darwin.tar.gz"
            )
