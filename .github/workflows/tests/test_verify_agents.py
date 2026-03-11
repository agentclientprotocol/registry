import os
import stat
from pathlib import Path

from verify_agents import (
    build_installed_npx_command,
    ensure_executable,
    npm_package_bin_name,
    resolve_binary_executable,
    should_retry_npx_auth_with_install,
)


def test_resolve_binary_executable_renames_single_raw_binary(tmp_path: Path):
    raw_binary = tmp_path / "downloaded-binary"
    raw_binary.write_text("#!/bin/sh\n")

    resolved = resolve_binary_executable(tmp_path, "./agent")

    assert resolved == tmp_path / "agent"
    assert resolved.exists()
    assert not raw_binary.exists()


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
