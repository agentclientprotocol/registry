#!/usr/bin/env python3
"""Verify all registered agents can be launched in isolated sandboxes.

Sandboxes are created in .sandbox/<dist_type>/<agent_id>/ for easy inspection.
Supports optional ACP auth verification via --auth-check flag.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from typing import NamedTuple

# Import auth client (only needed when --auth-check is used)
try:
    from client import AuthCheckResult, run_auth_check
    HAS_AUTH_CLIENT = True
except ImportError:
    HAS_AUTH_CLIENT = False

# Platform detection
PLATFORM_MAP = {
    ("Darwin", "arm64"): "darwin-aarch64",
    ("Darwin", "x86_64"): "darwin-x86_64",
    ("Linux", "aarch64"): "linux-aarch64",
    ("Linux", "x86_64"): "linux-x86_64",
    ("Windows", "AMD64"): "windows-x86_64",
    ("Windows", "ARM64"): "windows-aarch64",
}

DEFAULT_TIMEOUT = 10  # seconds
STARTUP_GRACE = 2  # seconds to wait before checking if process is alive
DEFAULT_SANDBOX_DIR = ".sandbox"
DEFAULT_AUTH_TIMEOUT = 60  # seconds for ACP handshake (includes npx download time)


class Result(NamedTuple):
    agent_id: str
    dist_type: str
    success: bool
    message: str
    skipped: bool = False


def get_current_platform() -> str:
    """Get current platform identifier."""
    system = platform.system()
    machine = platform.machine()
    return PLATFORM_MAP.get((system, machine), f"{system.lower()}-{machine}")


def check_command_exists(cmd: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(cmd) is not None


def download_file(url: str, dest: Path) -> bool:
    """Download a file from URL with progress."""
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "ACP-Registry-Verifier/1.0")
        with urllib.request.urlopen(req, timeout=60) as response:
            total = response.headers.get("Content-Length")
            if total:
                total = int(total)
                print(f"      Downloading {total / 1024 / 1024:.1f} MB...", end="", flush=True)
            else:
                print(f"      Downloading...", end="", flush=True)
            data = response.read()
            dest.write_bytes(data)
            print(f" done ({len(data) / 1024 / 1024:.1f} MB)")
        return True
    except Exception as e:
        print(f"\n      Download failed: {e}")
        return False


def extract_archive(archive: Path, dest: Path) -> bool:
    """Extract archive to destination."""
    try:
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(dest)
        elif archive.name.endswith(".tar.gz") or archive.name.endswith(".tgz"):
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(dest, filter="data")
        elif archive.name.endswith(".tar.bz2"):
            with tarfile.open(archive, "r:bz2") as tf:
                tf.extractall(dest, filter="data")
        elif archive.name.endswith(".tar"):
            with tarfile.open(archive, "r") as tf:
                tf.extractall(dest, filter="data")
        else:
            # Single file (like .exe or raw binary)
            shutil.copy(archive, dest / archive.name)
        return True
    except Exception as e:
        print(f"    Extraction failed: {e}")
        return False


def run_process(cmd: list[str], cwd: Path, env: dict, timeout: int) -> tuple[int | None, str, str]:
    """Run a process with timeout, return (exit_code, stdout, stderr)."""
    full_env = os.environ.copy()
    full_env.update(env)

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=full_env,
            stdin=subprocess.DEVNULL,  # Provide empty stdin
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return proc.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            # Process still running after timeout - this is often good (waiting for input)
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
            return None, "", "(process was still running - terminated)"

    except FileNotFoundError as e:
        return -1, "", f"Command not found: {e}"
    except Exception as e:
        return -1, "", f"Execution error: {e}"


def verify_binary(agent: dict, sandbox: Path, timeout: int, verbose: bool) -> Result:
    """Verify binary distribution."""
    agent_id = agent["id"]
    current_platform = get_current_platform()
    binary_dist = agent["distribution"].get("binary", {})

    if current_platform not in binary_dist:
        return Result(agent_id, "binary", False, f"No build for {current_platform}", skipped=True)

    target = binary_dist[current_platform]
    archive_url = target["archive"]
    cmd = target["cmd"]
    args = target.get("args", [])
    env = target.get("env", {})

    # Download (skip if already exists)
    archive_name = archive_url.split("/")[-1]
    archive_path = sandbox / archive_name
    extract_dir = sandbox / "extracted"

    if not archive_path.exists():
        print(f"    → Downloading from: {archive_url[:80]}...")
        if not download_file(archive_url, archive_path):
            return Result(agent_id, "binary", False, "Download failed")
    else:
        print(f"    → Using cached archive: {archive_name}")

    # Extract (skip if already extracted)
    if not extract_dir.exists():
        print(f"    → Extracting archive...")
        extract_dir.mkdir()
        if not extract_archive(archive_path, extract_dir):
            return Result(agent_id, "binary", False, "Extraction failed")
    else:
        print(f"    → Using cached extraction")

    # Find executable
    if cmd.startswith("./"):
        cmd = cmd[2:]

    # Check if cmd is a system command (node, python, etc.)
    if cmd in ("node", "python", "python3", "java", "ruby"):
        system_cmd = shutil.which(cmd)
        if not system_cmd:
            return Result(agent_id, "binary", False, f"System command not found: {cmd}", skipped=True)
        # For system commands, the working directory should be the extract_dir
        exe_path = Path(system_cmd)
        # Args should reference files in extract_dir
    else:
        # Look for the executable (might be in subdirectory)
        exe_path = None

        # First try exact match
        for path in extract_dir.rglob(cmd):
            exe_path = path
            break

        # If not found, try raw binary (file downloaded without archive)
        if not exe_path:
            # Check if there's only one file in extract_dir (raw binary case)
            files_in_extract = list(extract_dir.iterdir())
            if len(files_in_extract) == 1 and files_in_extract[0].is_file():
                # Rename the raw binary to expected name
                raw_file = files_in_extract[0]
                expected_path = extract_dir / cmd
                if not expected_path.exists():
                    raw_file.rename(expected_path)
                exe_path = expected_path

        if not exe_path:
            # Try direct path
            exe_path = extract_dir / cmd

        if not exe_path.exists():
            return Result(agent_id, "binary", False, f"Executable not found: {cmd}")

    # Make executable on Unix
    if platform.system() != "Windows":
        exe_path.chmod(exe_path.stat().st_mode | 0o755)

    # Run
    print(f"    → Running: {exe_path.name} {' '.join(args)}")

    full_cmd = [str(exe_path)] + args
    exit_code, stdout, stderr = run_process(full_cmd, extract_dir, env, timeout)

    # Check result
    if exit_code is None:
        # Process was still running - good sign
        return Result(agent_id, "binary", True, "Started successfully (terminated after timeout)")
    elif exit_code == 0:
        return Result(agent_id, "binary", True, "Exited cleanly")
    else:
        combined = (stdout + stderr).lower()
        # Check if it's a "needs input" error (still means binary works)
        if "input" in combined or "prompt" in combined or "stdin" in combined:
            return Result(agent_id, "binary", True, "Binary works (needs input)")
        # Check for environment issues (keyring, permissions, config files, etc.) - binary works but env fails
        env_issues = [
            "keyring", "keychain", "credential", "permission denied", "access denied",
            "configuration file not found", "config file not found", "providers.json",
            "cannot find package", "module_not_found", "cannot find module",
            "accepts 1 arg", "required argument", "missing argument", "agent-file",
        ]
        if any(issue in combined for issue in env_issues):
            return Result(agent_id, "binary", True, "Binary works (env setup needed)")
        msg = stderr[:200] if stderr else f"Exit code: {exit_code}"
        return Result(agent_id, "binary", False, msg)


def verify_npx(agent: dict, sandbox: Path, timeout: int, verbose: bool) -> Result:
    """Verify npx distribution."""
    agent_id = agent["id"]

    if not check_command_exists("npm"):
        return Result(agent_id, "npx", False, "npm not installed", skipped=True)

    npx_dist = agent["distribution"].get("npx", {})
    package = npx_dist.get("package", "")
    args = npx_dist.get("args", [])
    env = npx_dist.get("env", {})

    print(f"    → Running: npx {package} {' '.join(args)}")

    cmd = ["npx", "--prefix", str(sandbox), "--yes", package] + args
    exit_code, stdout, stderr = run_process(cmd, sandbox, env, timeout)

    if exit_code is None:
        return Result(agent_id, "npx", True, "Started successfully (terminated after timeout)")
    elif exit_code == 0:
        return Result(agent_id, "npx", True, "Exited cleanly")
    else:
        # Check if it's a "needs input" error (still means package works)
        combined = (stdout + stderr).lower()
        if "input" in combined or "prompt" in combined or "stdin" in combined:
            return Result(agent_id, "npx", True, "Package works (needs input)")
        msg = stderr[:200] if stderr else f"Exit code: {exit_code}"
        return Result(agent_id, "npx", False, msg)


def verify_uvx(agent: dict, sandbox: Path, timeout: int, verbose: bool) -> Result:
    """Verify uvx distribution."""
    agent_id = agent["id"]

    if not check_command_exists("uv"):
        return Result(agent_id, "uvx", False, "uv not installed", skipped=True)

    uvx_dist = agent["distribution"].get("uvx", {})
    package = uvx_dist.get("package", "")
    args = uvx_dist.get("args", [])
    env = uvx_dist.get("env", {})

    print(f"    → Running: uvx {package} {' '.join(args)}")

    cache_dir = sandbox / "uv-cache"
    cache_dir.mkdir(exist_ok=True)

    cmd = ["uvx", "--cache-dir", str(cache_dir), package] + args
    exit_code, stdout, stderr = run_process(cmd, sandbox, env, timeout)

    if exit_code is None:
        return Result(agent_id, "uvx", True, "Started successfully (terminated after timeout)")
    elif exit_code == 0:
        return Result(agent_id, "uvx", True, "Exited cleanly")
    else:
        # Check if it's a "needs input" error (still means package works)
        combined = (stdout + stderr).lower()
        if "input" in combined or "prompt" in combined or "stdin" in combined:
            return Result(agent_id, "uvx", True, "Package works (needs input)")
        # Filter out download progress noise from stderr
        error_lines = [
            line for line in stderr.split("\n")
            if line.strip() and not line.strip().startswith(("Downloading", "Installed", " "))
        ]
        msg = "\n".join(error_lines[:5]) if error_lines else f"Exit code: {exit_code}"
        return Result(agent_id, "uvx", False, msg[:200])


def prepare_binary(agent: dict, sandbox: Path) -> tuple[bool, str]:
    """Download and extract binary distribution if needed.

    Returns:
        (success, message) tuple
    """
    current_platform = get_current_platform()
    binary_dist = agent["distribution"].get("binary", {})

    if current_platform not in binary_dist:
        return False, f"No build for {current_platform}"

    target = binary_dist[current_platform]
    archive_url = target["archive"]

    # Download (skip if already exists)
    archive_name = archive_url.split("/")[-1]
    archive_path = sandbox / archive_name
    extract_dir = sandbox / "extracted"

    if not archive_path.exists():
        print(f"    → Downloading from: {archive_url[:80]}...")
        if not download_file(archive_url, archive_path):
            return False, "Download failed"

    # Extract (skip if already extracted)
    if not extract_dir.exists():
        print(f"    → Extracting archive...")
        extract_dir.mkdir()
        if not extract_archive(archive_path, extract_dir):
            return False, "Extraction failed"

    return True, "Binary prepared"


def build_agent_command(agent: dict, dist_type: str, sandbox: Path) -> tuple[list[str], Path, dict[str, str]]:
    """Build command, working directory, and env for an agent distribution.

    Returns:
        (cmd, cwd, env) tuple
    """
    distribution = agent["distribution"]
    env: dict[str, str] = {}

    if dist_type == "npx":
        npx_dist = distribution.get("npx", {})
        package = npx_dist.get("package", "")
        args = npx_dist.get("args", [])
        env = npx_dist.get("env", {})
        cmd = ["npx", "--prefix", str(sandbox), "--yes", package] + args
        cwd = sandbox
    elif dist_type == "uvx":
        uvx_dist = distribution.get("uvx", {})
        package = uvx_dist.get("package", "")
        args = uvx_dist.get("args", [])
        env = uvx_dist.get("env", {})
        cache_dir = sandbox / "uv-cache"
        cache_dir.mkdir(exist_ok=True)
        cmd = ["uvx", "--cache-dir", str(cache_dir), package] + args
        cwd = sandbox
    elif dist_type == "binary":
        current_platform = get_current_platform()
        binary_dist = distribution.get("binary", {})
        target = binary_dist.get(current_platform, {})
        args = target.get("args", [])
        env = target.get("env", {})
        extract_dir = sandbox / "extracted"

        # Find the executable
        target_cmd = target.get("cmd", "")
        if target_cmd.startswith("./"):
            target_cmd = target_cmd[2:]

        if target_cmd in ("node", "python", "python3", "java", "ruby"):
            exe_path = Path(shutil.which(target_cmd) or target_cmd)
        else:
            exe_path = None
            for path in extract_dir.rglob(target_cmd):
                exe_path = path
                break
            if not exe_path:
                exe_path = extract_dir / target_cmd

        cmd = [str(exe_path)] + args
        cwd = extract_dir
    else:
        cmd = []
        cwd = sandbox

    return cmd, cwd, env


def verify_auth(
    agent: dict,
    dist_type: str,
    sandbox: Path,
    auth_timeout: float,
    verbose: bool,
) -> Result:
    """Verify agent supports ACP authentication.

    Args:
        agent: Agent configuration dict
        dist_type: Distribution type to test
        sandbox: Sandbox directory
        auth_timeout: Timeout for ACP handshake
        verbose: Enable verbose output

    Returns:
        Result indicating auth check pass/fail
    """
    agent_id = agent["id"]

    if not HAS_AUTH_CLIENT:
        return Result(agent_id, dist_type, False,
                      "Auth client not available", skipped=True)

    # For binary distributions, ensure download and extraction first
    if dist_type == "binary":
        success, message = prepare_binary(agent, sandbox)
        if not success:
            return Result(agent_id, dist_type, False, message, skipped=True)

    # Build command for this distribution
    cmd, cwd, agent_env = build_agent_command(agent, dist_type, sandbox)

    if not cmd:
        return Result(agent_id, dist_type, False,
                      f"Cannot build command for {dist_type}", skipped=True)

    # Create isolated environment with sandbox HOME
    auth_sandbox = sandbox / "auth-home"
    auth_sandbox.mkdir(exist_ok=True)
    env = {
        "HOME": str(auth_sandbox),
        **agent_env,
    }

    if verbose:
        print(f"    → Auth check: {' '.join(cmd[:3])}...")

    # Run auth check
    result = run_auth_check(cmd, cwd, env, auth_timeout)

    if result.success:
        methods_info = ", ".join(
            f"{m.id}({m.type})" for m in result.auth_methods if m.type
        )
        return Result(agent_id, dist_type, True, f"Auth OK: {methods_info}")
    else:
        return Result(agent_id, dist_type, False, result.error or "Auth check failed")


def verify_agent(
    agent: dict,
    dist_type: str | None,
    timeout: int,
    verbose: bool,
    sandbox_base: Path,
    clean: bool = False,
    auth_check: bool = False,
    auth_timeout: float = DEFAULT_AUTH_TIMEOUT,
) -> list[Result]:
    """Verify an agent's distributions.

    Args:
        agent: Agent configuration dict
        dist_type: Specific distribution type to test, or None for all
        timeout: Process timeout in seconds
        verbose: Enable verbose output
        sandbox_base: Base directory for sandboxes (.sandbox/)
        clean: If True, clean sandbox before running
        auth_check: If True, run ACP auth verification instead of basic launch test
        auth_timeout: Timeout for ACP handshake in seconds
    """
    agent_id = agent["id"]
    results = []
    distribution = agent.get("distribution", {})

    # Determine which distributions to test
    dist_types = [dist_type] if dist_type else list(distribution.keys())

    for dtype in dist_types:
        if dtype not in distribution:
            continue

        print(f"  Testing {dtype}...")

        # Create sandbox: .sandbox/<dist_type>/<agent_id>/
        sandbox = sandbox_base / dtype / agent_id

        if clean and sandbox.exists():
            # For binary, only clean extracted dir, keep downloaded archives
            if dtype == "binary":
                extracted = sandbox / "extracted"
                if extracted.exists():
                    print(f"    Cleaning extracted files (keeping downloads)...")
                    shutil.rmtree(extracted, ignore_errors=True)
            else:
                print(f"    Cleaning sandbox...")
                shutil.rmtree(sandbox, ignore_errors=True)

        sandbox.mkdir(parents=True, exist_ok=True)

        # Run either auth check (deeper) or basic launch test
        if auth_check:
            result = verify_auth(agent, dtype, sandbox, auth_timeout, verbose)
        elif dtype == "binary":
            result = verify_binary(agent, sandbox, timeout, verbose)
        elif dtype == "npx":
            result = verify_npx(agent, sandbox, timeout, verbose)
        elif dtype == "uvx":
            result = verify_uvx(agent, sandbox, timeout, verbose)
        else:
            result = Result(agent_id, dtype, False, f"Unknown distribution type: {dtype}", skipped=True)

        results.append(result)

        # Print result
        if result.skipped:
            print(f"    ⊘ Skipped: {result.message}")
        elif result.success:
            print(f"    ✓ Success: {result.message}")
        else:
            print(f"    ✗ Failed: {result.message}")

        if verbose:
            print(f"    Sandbox: {sandbox}")

    return results


def load_quarantine(registry_dir: Path) -> dict[str, str]:
    """Load quarantine list from registry directory.

    Returns:
        Dict mapping agent_id to quarantine reason.
    """
    quarantine_path = registry_dir / "quarantine.json"
    if not quarantine_path.exists():
        return {}
    try:
        with open(quarantine_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: Could not read {quarantine_path}: {e}")
        return {}


def load_registry(registry_dir: Path) -> list[dict]:
    """Load all agents from registry directory, excluding quarantined ones."""
    agents = []
    skip_dirs = {".claude", ".git", ".github", ".idea", "__pycache__", "dist", "_not_yet_unsupported"}
    quarantine = load_quarantine(registry_dir)

    for agent_dir in sorted(registry_dir.iterdir()):
        if not agent_dir.is_dir() or agent_dir.name in skip_dirs:
            continue

        agent_json = agent_dir / "agent.json"
        if not agent_json.exists():
            continue

        try:
            with open(agent_json) as f:
                agent = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid JSON in {agent_json}: {e}")
            continue

        agent_id = agent.get("id", agent_dir.name)
        if agent_id in quarantine:
            print(f"  ⊘ Quarantined {agent_id}: {quarantine[agent_id]}")
            continue

        agents.append(agent)

    if quarantine:
        print(f"  ({len(quarantine)} agent(s) quarantined)")
        print()

    return agents


def main():
    parser = argparse.ArgumentParser(
        description="Verify ACP agents can be launched in isolated sandboxes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Verify all agents (basic launch test)
  %(prog)s -a claude,gemini         # Verify specific agents (comma-separated)
  %(prog)s -t npx                   # Verify only npx distributions
  %(prog)s --clean                  # Clean sandboxes before running
  %(prog)s --clean-all              # Remove all sandboxes and exit
  %(prog)s --auth-check             # Verify ACP auth support (deeper test)
""",
    )
    parser.add_argument("--agent", "-a", help="Verify specific agent IDs (comma-separated)")
    parser.add_argument("--type", "-t", choices=["binary", "npx", "uvx"],
                        help="Verify specific distribution type only")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"Process timeout in seconds (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--sandbox-dir", "-s", default=DEFAULT_SANDBOX_DIR,
                        help=f"Sandbox directory (default: {DEFAULT_SANDBOX_DIR})")
    parser.add_argument("--clean", "-c", action="store_true",
                        help="Clean agent sandbox before running")
    parser.add_argument("--clean-all", action="store_true",
                        help="Remove all sandboxes and exit")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")
    parser.add_argument("--auth-check", action="store_true",
                        help="Verify ACP auth support instead of basic launch test (requires agent-client-protocol)")
    parser.add_argument("--auth-timeout", type=float, default=DEFAULT_AUTH_TIMEOUT,
                        help=f"ACP handshake timeout in seconds (default: {DEFAULT_AUTH_TIMEOUT})")
    args = parser.parse_args()

    # Always show what's happening
    verbose = True  # Force verbose mode for better visibility

    # Check auth client availability if auth flag is used
    if args.auth_check and not HAS_AUTH_CLIENT:
        print("Error: --auth-check/--auth-only requires 'agent-client-protocol' package")
        print("Install with: pip install agent-client-protocol")
        print("Or run with: uv run --with agent-client-protocol ...")
        sys.exit(1)

    # Find registry directory
    registry_dir = Path(__file__).parent.parent.parent
    sandbox_base = registry_dir / args.sandbox_dir

    # Handle --clean-all
    if args.clean_all:
        if sandbox_base.exists():
            print(f"Removing all sandboxes: {sandbox_base}")
            shutil.rmtree(sandbox_base)
            print("Done.")
        else:
            print(f"No sandboxes found at: {sandbox_base}")
        return

    print(f"Platform: {get_current_platform()}")
    print(f"Registry: {registry_dir}")
    print(f"Sandbox:  {sandbox_base}")
    print()

    # Load agents
    agents = load_registry(registry_dir)
    print(f"Found {len(agents)} agents")
    print()

    # Filter if specific agents requested (comma-separated)
    quarantine = load_quarantine(registry_dir)
    if args.agent:
        requested_ids = [a.strip() for a in args.agent.split(",")]
        all_agent_ids = [a["id"] for a in agents]

        # Check for invalid agent IDs (quarantined agents are valid but skipped)
        invalid = [aid for aid in requested_ids if aid not in all_agent_ids and aid not in quarantine]
        if invalid:
            print(f"Unknown agent(s): {', '.join(invalid)}")
            print(f"Available: {', '.join(all_agent_ids)}")
            sys.exit(1)

        agents = [a for a in agents if a["id"] in requested_ids]
        print(f"Verifying {len(agents)} agent(s): {', '.join(a['id'] for a in agents)}")
        print()

    # Verify each agent
    all_results = []
    total = len(agents)
    for idx, agent in enumerate(agents, 1):
        agent_id = agent["id"]
        dist_types = list(agent.get("distribution", {}).keys())
        print(f"[{idx}/{total}] {agent_id} ({', '.join(dist_types)})")

        results = verify_agent(
            agent,
            dist_type=args.type,
            timeout=args.timeout,
            verbose=verbose,
            sandbox_base=sandbox_base,
            clean=args.clean,
            auth_check=args.auth_check,
            auth_timeout=args.auth_timeout,
        )

        all_results.extend(results)
        print()

    # Summary
    passed = [r for r in all_results if r.success and not r.skipped]
    failed = [r for r in all_results if not r.success and not r.skipped]
    skipped = [r for r in all_results if r.skipped]

    print("=" * 50)
    print("Summary")
    print("=" * 50)
    print(f"  Passed:  {len(passed)}")
    print(f"  Failed:  {len(failed)}")
    print(f"  Skipped: {len(skipped)}")
    print()

    if failed:
        print("Failed tests:")
        for r in failed:
            print(f"  - {r.agent_id} ({r.dist_type}): {r.message}")
        sys.exit(1)

    print("All tests passed!")
    print(f"\nSandboxes available at: {sandbox_base}")


if __name__ == "__main__":
    main()
