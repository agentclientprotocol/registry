"""Tests for shared registry utilities."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from registry_utils import (
    extract_npm_package_name,
    extract_npm_package_version,
    extract_pypi_package_name,
    load_quarantine,
    normalize_version,
    should_skip_dir,
    validate_distribution_urls,
)


class TestExtractNpmPackageName:
    def test_scoped_with_version(self):
        assert extract_npm_package_name("@google/gemini-cli@0.30.0") == "@google/gemini-cli"

    def test_scoped_without_version(self):
        assert extract_npm_package_name("@google/gemini-cli") == "@google/gemini-cli"

    def test_unscoped_with_version(self):
        assert extract_npm_package_name("some-package@1.2.3") == "some-package"

    def test_unscoped_without_version(self):
        assert extract_npm_package_name("some-package") == "some-package"

    def test_empty_string(self):
        assert extract_npm_package_name("") == ""


class TestExtractNpmPackageVersion:
    def test_scoped_with_version(self):
        assert extract_npm_package_version("@google/gemini-cli@0.30.0") == "0.30.0"

    def test_scoped_without_version(self):
        assert extract_npm_package_version("@google/gemini-cli") is None

    def test_unscoped_with_version(self):
        assert extract_npm_package_version("some-package@1.2.3") == "1.2.3"

    def test_unscoped_without_version(self):
        assert extract_npm_package_version("some-package") is None


class TestExtractPypiPackageName:
    def test_with_double_equals(self):
        assert extract_pypi_package_name("some-package==1.2.3") == "some-package"

    def test_with_at_version(self):
        assert extract_pypi_package_name("some-package@1.2.3") == "some-package"

    def test_with_gte(self):
        assert extract_pypi_package_name("some-package>=1.0") == "some-package"

    def test_plain_name(self):
        assert extract_pypi_package_name("some-package") == "some-package"


class TestNormalizeVersion:
    def test_already_semver(self):
        assert normalize_version("1.2.3") == "1.2.3"

    def test_two_parts(self):
        assert normalize_version("1.2") == "1.2.0"

    def test_one_part(self):
        assert normalize_version("1") == "1.0.0"

    def test_four_parts_truncated(self):
        assert normalize_version("1.2.3.4") == "1.2.3"


class TestLoadQuarantine:
    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            assert load_quarantine(Path(d)) == {}

    def test_empty_object(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "quarantine.json"
            p.write_text("{}")
            assert load_quarantine(Path(d)) == {}

    def test_with_entries(self):
        with tempfile.TemporaryDirectory() as d:
            data = {"bad-agent": "broke auth", "other": "removed"}
            p = Path(d) / "quarantine.json"
            p.write_text(json.dumps(data))
            assert load_quarantine(Path(d)) == data

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "quarantine.json"
            p.write_text("not json")
            assert load_quarantine(Path(d)) == {}


class TestValidateDistributionUrls:
    """Distribution URL validation (moved from build_registry.py)."""

    def test_returns_no_errors_when_all_urls_reachable(self):
        distribution = {
            "binary": {
                "darwin-aarch64": {
                    "archive": "https://example.com/agent-darwin.tar.gz",
                    "cmd": "./agent",
                },
                "linux-x86_64": {
                    "archive": "https://example.com/agent-linux.tar.gz",
                    "cmd": "./agent",
                },
            }
        }
        with patch("registry_utils.url_exists", return_value=True):
            assert validate_distribution_urls(distribution) == []

    def test_reports_unreachable_binary_archive(self):
        distribution = {
            "binary": {
                "darwin-aarch64": {
                    "archive": "https://example.com/ok.tar.gz",
                    "cmd": "./agent",
                },
                "windows-x86_64": {
                    "archive": "https://example.com/missing-windows.zip",
                    "cmd": "agent.exe",
                },
            }
        }

        def fake_url_exists(url, *_args, **_kwargs):
            return "missing" not in url

        with patch("registry_utils.url_exists", side_effect=fake_url_exists):
            errors = validate_distribution_urls(distribution)

        assert len(errors) == 1
        assert "windows-x86_64" in errors[0]
        assert "missing-windows.zip" in errors[0]

    def test_skip_url_validation_env_returns_empty(self, monkeypatch):
        monkeypatch.setenv("SKIP_URL_VALIDATION", "1")
        # Re-import to pick up the patched env var.
        import importlib

        import registry_utils

        importlib.reload(registry_utils)
        try:
            distribution = {
                "binary": {
                    "darwin-aarch64": {
                        "archive": "https://example.com/anything.tar.gz",
                        "cmd": "./agent",
                    }
                }
            }
            assert registry_utils.validate_distribution_urls(distribution) == []
        finally:
            monkeypatch.delenv("SKIP_URL_VALIDATION", raising=False)
            importlib.reload(registry_utils)


class TestShouldSkipDir:
    def test_skips_hidden_runtime_dirs(self):
        assert should_skip_dir(".sandbox")
        assert should_skip_dir(".matrix-sandbox-debug")
        assert should_skip_dir(".protocol-matrix-goose-check")
        assert should_skip_dir(".tmp-junie-run")

    def test_keeps_agent_dirs(self):
        assert not should_skip_dir("codex-acp")
