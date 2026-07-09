import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

from verify_agents import (
    build_agent_process_env,
    build_installed_npx_command,
    ensure_executable,
    extract_archive,
    npm_package_bin_name,
    prepare_npx_package,
    resolve_binary_executable,
    run_process,
    should_retry_npx_auth_with_install,
)


def test_resolve_binary_executable_renames_single_raw_binary(tmp_path: Path):
    raw_binary = tmp_path / "downloaded-binary"
    raw_binary.write_text("#!/bin/sh\n")

    resolved = resolve_binary_executable(tmp_path, "./agent")

    assert resolved == tmp_path / "agent"
    assert resolved.exists()
    assert not raw_binary.exists()


def test_build_agent_process_env_does_not_pass_github_context(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path / "repo"))
    monkeypatch.setenv("PATH", "/usr/bin")

    env = build_agent_process_env(
        {
            "AGENT_FLAG": "1",
            "GITHUB_TOKEN": "evil",
            "HOME": "/tmp/evil-home",
            "LD_PRELOAD": "/tmp/hook.so",
            "PATH": "/tmp/evil-bin",
        },
        tmp_path / "home",
        tmp_path / "tmp",
    )

    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == str(tmp_path / "home")
    assert env["AGENT_FLAG"] == "1"
    assert "GITHUB_TOKEN" not in env
    assert "GITHUB_WORKSPACE" not in env
    assert "LD_PRELOAD" not in env


def test_build_agent_process_env_can_prepend_trusted_paths(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("PATH", "/usr/bin")

    env = build_agent_process_env(
        {"PATH": "/tmp/evil-bin"},
        tmp_path / "home",
        tmp_path / "tmp",
        prepend_path=[str(tmp_path / "bin")],
    )

    assert env["PATH"] == f"{tmp_path / 'bin'}{os.pathsep}/usr/bin"


def test_run_process_ignores_manifest_home(tmp_path: Path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    evil_home = tmp_path / "evil-home"

    exit_code, stdout, stderr = run_process(
        [sys.executable, "-c", "import os; print(os.environ['HOME'])"],
        sandbox,
        {"HOME": str(evil_home)},
        2,
    )

    assert exit_code == 0
    assert stdout.strip() == str(sandbox / "home")
    assert stderr == ""
    assert not evil_home.exists()


def test_prepare_npx_package_ignores_manifest_home(monkeypatch, tmp_path: Path):
    captured_env = {}

    def fake_run(*args, **kwargs):
        captured_env.update(kwargs["env"])
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("verify_agents.subprocess.run", fake_run)

    evil_home = tmp_path / "evil-home"
    assert prepare_npx_package("example-agent@1.0.0", tmp_path, {"HOME": str(evil_home)}, 1) is None

    assert captured_env["HOME"] == str(tmp_path / "home")
    assert not evil_home.exists()


def test_prepare_npx_package_uses_trusted_home_dir(monkeypatch, tmp_path: Path):
    captured_env = {}

    def fake_run(*args, **kwargs):
        captured_env.update(kwargs["env"])
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("verify_agents.subprocess.run", fake_run)

    trusted_home = tmp_path / "auth-home"
    evil_home = tmp_path / "evil-home"
    assert (
        prepare_npx_package(
            "example-agent@1.0.0",
            tmp_path,
            {"HOME": str(evil_home)},
            1,
            home_dir=trusted_home,
        )
        is None
    )

    assert captured_env["HOME"] == str(trusted_home)
    assert not evil_home.exists()


def test_resolve_binary_executable_rejects_unsafe_paths(tmp_path: Path):
    assert resolve_binary_executable(tmp_path, "../agent") is None
    assert resolve_binary_executable(tmp_path, "/bin/sh") is None
    assert resolve_binary_executable(tmp_path, "C:\\Windows\\system32\\cmd.exe") is None


def test_resolve_binary_executable_accepts_windows_style_relative_path(tmp_path: Path):
    binary = tmp_path / "dist-package" / "cursor-agent.cmd"
    binary.parent.mkdir()
    binary.write_text("@echo off\n")

    resolved = resolve_binary_executable(tmp_path, "./dist-package\\cursor-agent.cmd")

    assert resolved == binary


def test_extract_archive_rejects_zip_path_traversal(tmp_path: Path):
    archive = tmp_path / "bad.zip"
    dest = tmp_path / "dest"

    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../outside.txt", "owned")

    assert not extract_archive(archive, dest)
    assert not dest.exists()
    assert not (tmp_path / "outside.txt").exists()


def test_extract_archive_rejects_late_zip_traversal_without_partial_cache(tmp_path: Path):
    archive = tmp_path / "bad.zip"
    dest = tmp_path / "dest"

    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("agent", "#!/bin/sh\n")
        zf.writestr("../outside.txt", "owned")

    assert not extract_archive(archive, dest)
    assert not dest.exists()
    assert not (tmp_path / "outside.txt").exists()


def test_extract_archive_rejects_zip_symlinks(tmp_path: Path):
    archive = tmp_path / "bad.zip"
    dest = tmp_path / "dest"

    info = zipfile.ZipInfo("agent-link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(info, "agent")

    assert not extract_archive(archive, dest)
    assert not dest.exists()


def test_extract_archive_allows_safe_zip_entries(tmp_path: Path):
    archive = tmp_path / "good.zip"
    dest = tmp_path / "dest"

    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("bin/agent", "#!/bin/sh\n")

    assert extract_archive(archive, dest)
    assert (dest / "bin" / "agent").read_text() == "#!/bin/sh\n"


def test_ensure_executable_adds_execute_bits(tmp_path: Path):
    binary = tmp_path / "tool"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o644)

    ensure_executable(binary)

    assert binary.stat().st_mode & stat.S_IXUSR
    assert os.access(binary, os.X_OK)


def test_npm_package_bin_name_uses_declared_bin(tmp_path: Path):
    package_dir = tmp_path / "node_modules" / "@jetbrains" / "junie"
    package_dir.mkdir(parents=True)
    (package_dir / "package.json").write_text(
        '{"name":"@jetbrains/junie","bin":{"junie":"bin/index.js"}}'
    )

    assert npm_package_bin_name("@jetbrains/junie@888.173.0", tmp_path) == "junie"


def test_build_installed_npx_command_prefers_home_shim(tmp_path: Path):
    package_dir = tmp_path / "node_modules" / "@jetbrains" / "junie"
    package_dir.mkdir(parents=True)
    (package_dir / "package.json").write_text(
        '{"name":"@jetbrains/junie","bin":{"junie":"bin/index.js"}}'
    )

    local_bin = tmp_path / "node_modules" / ".bin"
    local_bin.mkdir(parents=True)
    (local_bin / "junie").write_text("#!/bin/sh\n")

    auth_home = tmp_path / "auth-home"
    home_bin = auth_home / ".local" / "bin"
    home_bin.mkdir(parents=True)
    (home_bin / "junie").write_text("#!/bin/sh\n")

    command = build_installed_npx_command(
        "@jetbrains/junie@888.173.0",
        ["--acp=true"],
        tmp_path,
        auth_home,
    )

    assert command == [str(home_bin / "junie"), "--acp=true"]


def test_should_retry_npx_auth_with_install_on_shim_error():
    assert should_retry_npx_auth_with_install(
        "Timeout after 120s waiting for initialize response",
        "[Junie] Shim not found at /tmp/home/.local/bin/junie\nPlease reinstall: npm install",
    )
