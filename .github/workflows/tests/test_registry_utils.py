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
    load_quarantine,
    normalize_version,
    sanitize_agent_env,
    should_skip_dir,
    subprocess_group_kwargs,
    terminate_process_group,
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
