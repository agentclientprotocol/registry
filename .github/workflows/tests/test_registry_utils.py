"""Tests for shared registry utilities."""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from registry_utils import (
    extract_npm_package_name,
    extract_npm_package_version,
    extract_pypi_package_name,
    is_preview_version,
    load_quarantine,
    normalize_version,
    parse_preview_version,
    resolve_preview_entry,
    sanitize_agent_env,
    semver_sort_key,
    should_skip_dir,
    strip_preview,
    subprocess_group_kwargs,
    terminate_process_group,
    version_tuple,
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


class TestVersionTuple:
    def test_pads_short_versions(self):
        assert version_tuple("1") == (1, 0, 0)
        assert version_tuple("1.2") == (1, 2, 0)

    def test_keeps_extra_components(self):
        assert version_tuple("1.2.3.4") == (1, 2, 3, 4)

    def test_rejects_prerelease(self):
        with pytest.raises(ValueError):
            version_tuple("1.9.0-preview.1")


class TestParsePreviewVersion:
    def test_parses_preview(self):
        assert parse_preview_version("1.9.0-preview.3") == ((1, 9, 0), 3)

    def test_plain_release_is_not_preview(self):
        assert parse_preview_version("1.9.0") is None
        assert not is_preview_version("1.9.0")

    @pytest.mark.parametrize(
        "version",
        [
            "1.0-preview-1",
            "1.0-preview.1",
            "1.9.0-preview",
            "1.9.0-preview.",
            "1.9.0-rc.1",
            "1.9.0-next.1",
            "1.9.0+preview.1",
            "v1.9.0-preview.1",
            "",
        ],
    )
    def test_rejects_unsupported_shapes(self, version):
        assert parse_preview_version(version) is None
        assert not is_preview_version(version)


class TestSemverSortKey:
    def test_total_ordering(self):
        ordered = [
            "1.9.0-preview.2",
            "1.9.0-preview.10",
            "1.9.0",
            "1.9.1-preview.1",
            "1.9.1",
        ]
        assert sorted(ordered, key=semver_sort_key) == ordered

    def test_numeric_counter_comparison(self):
        assert semver_sort_key("1.9.0-preview.10") > semver_sort_key("1.9.0-preview.2")

    def test_prerelease_ranks_below_its_release(self):
        assert semver_sort_key("1.9.0-preview.99") < semver_sort_key("1.9.0")

    def test_release_ranks_below_next_prerelease(self):
        assert semver_sort_key("1.9.0") < semver_sort_key("1.9.1-preview.1")


def _agent(version: str, preview: dict | None = None) -> dict:
    agent = {
        "id": "codex-acp",
        "name": "Codex",
        "version": version,
        "description": "ACP adapter",
        "repository": "https://github.com/agentclientprotocol/codex-acp",
        "authors": ["OpenAI"],
        "license": "proprietary",
        "distribution": {
            "npx": {
                "package": f"@agentclientprotocol/codex-acp@{version}",
                "args": ["--stable-flag"],
            }
        },
    }
    if preview is not None:
        agent["preview"] = preview
    return agent


def _preview(version: str) -> dict:
    return {
        "version": version,
        "distribution": {"npx": {"package": f"@agentclientprotocol/codex-acp@{version}"}},
    }


class TestStripPreview:
    def test_removes_preview_block(self):
        agent = _agent("1.8.0", _preview("1.9.0-preview.1"))

        stripped = strip_preview(agent)

        assert "preview" not in stripped
        assert stripped["version"] == "1.8.0"
        assert "preview" in agent  # input untouched

    def test_no_preview_block_is_a_copy(self):
        agent = _agent("1.8.0")

        stripped = strip_preview(agent)

        assert stripped == agent
        assert stripped["distribution"] is not agent["distribution"]


class TestResolvePreviewEntry:
    def test_no_preview_block_returns_base_entry(self):
        agent = _agent("1.8.0")

        assert resolve_preview_entry(agent) == agent

    def test_preview_ahead_substitutes_version_and_distribution(self):
        agent = _agent("1.8.0", _preview("1.9.0-preview.1"))

        entry = resolve_preview_entry(agent)

        assert "preview" not in entry
        assert entry["version"] == "1.9.0-preview.1"
        assert entry["distribution"] == {
            "npx": {"package": "@agentclientprotocol/codex-acp@1.9.0-preview.1"}
        }
        for field in ("id", "name", "description", "repository", "authors", "license"):
            assert entry[field] == agent[field]
        assert list(entry.keys()) == [k for k in agent if k != "preview"]

    def test_stable_ahead_falls_back_to_base_entry(self):
        agent = _agent("1.9.1", _preview("1.9.0-preview.1"))

        entry = resolve_preview_entry(agent)

        assert entry == strip_preview(agent)
        assert entry["version"] == "1.9.1"

    def test_equal_versions_fall_back_to_base_entry(self):
        agent = _agent("1.9.1", _preview("1.9.1"))

        entry = resolve_preview_entry(agent)

        assert entry == strip_preview(agent)

    def test_plain_release_preview_ahead_is_substituted(self):
        agent = _agent("1.9.0", _preview("1.9.1"))

        entry = resolve_preview_entry(agent)

        assert entry["version"] == "1.9.1"
        assert entry["distribution"]["npx"]["package"].endswith("@1.9.1")
        assert "preview" not in entry

    def test_result_is_detached_from_input(self):
        agent = _agent("1.8.0", _preview("1.9.0-preview.1"))

        entry = resolve_preview_entry(agent)
        entry["distribution"]["npx"]["package"] = "mutated"

        assert agent["preview"]["distribution"]["npx"]["package"] != "mutated"


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


class TestShouldSkipDir:
    def test_skips_hidden_runtime_dirs(self):
        assert should_skip_dir(".sandbox")
        assert should_skip_dir(".matrix-sandbox-debug")
        assert should_skip_dir(".protocol-matrix-goose-check")
        assert should_skip_dir(".tmp-junie-run")

    def test_keeps_agent_dirs(self):
        assert not should_skip_dir("codex-acp")


class TestSanitizeAgentEnv:
    def test_keeps_agent_specific_flags(self):
        env = sanitize_agent_env(
            {
                "VT_ACP_ENABLED": "1",
                "DROID_DISABLE_AUTO_UPDATE": "true",
            }
        )

        assert env == {
            "VT_ACP_ENABLED": "1",
            "DROID_DISABLE_AUTO_UPDATE": "true",
        }

    def test_drops_runner_credentials_and_launch_overrides(self):
        env = sanitize_agent_env(
            {
                "AGENT_FLAG": "1",
                "GITHUB_TOKEN": "secret",
                "GITHUB_WORKSPACE": "/repo",
                "HOME": "/tmp/evil",
                "LD_PRELOAD": "/tmp/hook.so",
                "PATH": "/tmp/bin",
                "RUNNER_TEMP": "/tmp/runner",
                "SSH_AUTH_SOCK": "/tmp/ssh.sock",
            }
        )

        assert env == {"AGENT_FLAG": "1"}

    def test_drops_reserved_names_case_insensitively(self):
        env = sanitize_agent_env(
            {
                "AGENT_FLAG": "1",
                "Path": "/tmp/bin",
                "SYSTEMROOT": "C:\\Windows",
                "github_token": "secret",
                "pythonpath": "/tmp/python",
            }
        )

        assert env == {"AGENT_FLAG": "1"}


@pytest.mark.skipif(os.name == "nt", reason="process group behavior differs on Windows")
def test_terminate_process_group_kills_background_child(tmp_path: Path):
    marker = tmp_path / "child-ran"
    child_script = (
        f"import pathlib, time; time.sleep(0.4); pathlib.Path({str(marker)!r}).write_text('ran')"
    )
    parent_script = (
        "import subprocess, sys; "
        f"subprocess.Popen([{sys.executable!r}, '-c', {child_script!r}]); "
        "sys.exit(0)"
    )
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            parent_script,
        ],
        **subprocess_group_kwargs(),
    )
    proc.wait(timeout=2)

    terminate_process_group(proc)
    time.sleep(0.6)

    assert not marker.exists()


@pytest.mark.skipif(os.name == "nt", reason="process group behavior differs on Windows")
def test_terminate_process_group_kills_sigterm_ignoring_child_after_parent_exits(tmp_path: Path):
    ready = tmp_path / "child-ready"
    marker = tmp_path / "child-ran"
    child_script = (
        "import pathlib, signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"pathlib.Path({str(ready)!r}).write_text('ready'); "
        "time.sleep(0.4); "
        f"pathlib.Path({str(marker)!r}).write_text('ran')"
    )
    parent_script = (
        "import subprocess, sys; "
        f"subprocess.Popen([{sys.executable!r}, '-c', {child_script!r}]); "
        "sys.exit(0)"
    )
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            parent_script,
        ],
        **subprocess_group_kwargs(),
    )
    proc.wait(timeout=2)

    deadline = time.monotonic() + 2
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ready.exists()

    terminate_process_group(proc, timeout=0.1)
    time.sleep(0.6)

    assert not marker.exists()
