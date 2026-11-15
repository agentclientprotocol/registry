import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def run_wrapper(tmp_path):
    workflows = tmp_path / ".github" / "workflows"
    scripts = workflows / "scripts"
    scripts.mkdir(parents=True)
    wrapper = scripts / "run-registry-docker.sh"
    shutil.copy2(Path(__file__).parents[1] / "scripts" / wrapper.name, wrapper)
    dockerfile = workflows / "docker" / "registry-tools.Dockerfile"
    dockerfile.parent.mkdir()
    dockerfile.write_text("FROM node:22-bookworm-slim\n")
    file_hash = hashlib.sha256(dockerfile.read_bytes()).hexdigest()
    build_hash = hashlib.sha256(f"{file_hash}  {dockerfile}\n".encode()).hexdigest()

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        f"""#!{sys.executable}
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["DOCKER_CALLS"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if args[:2] == ["image", "inspect"]:
    if os.environ["IMAGE_EXISTS"] == "0":
        sys.exit(1)
    if "--format" in args:
        fmt = args[args.index("--format") + 1]
        print("linux/amd64" if ".Os" in fmt else "org.openai.acp-registry.build-hash={build_hash}")
elif args[0] == "build":
    sys.exit(int(os.environ.get("BUILD_EXIT", "0")))
"""
    )
    docker.chmod(0o755)
    calls_file = tmp_path / "calls.jsonl"

    def run(mode, *, image_exists=True, build_exit=0):
        result = subprocess.run(
            ["bash", str(wrapper), "node", "--version"],
            env={
                **os.environ,
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "ACP_REGISTRY_BUILD_IMAGE": mode,
                "ACP_REGISTRY_DOCKER_PLATFORM": "linux/amd64",
                "DOCKER_CALLS": str(calls_file),
                "IMAGE_EXISTS": str(int(image_exists)),
                "BUILD_EXIT": str(build_exit),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        calls = (
            [json.loads(line) for line in calls_file.read_text().splitlines()]
            if calls_file.exists()
            else []
        )
        return result, calls

    return run


@pytest.mark.parametrize(
    ("mode", "image_exists", "should_build", "refresh"),
    [
        ("auto", True, False, False),
        ("auto", False, True, False),
        ("1", True, True, False),
        ("0", False, False, False),
        ("refresh", True, True, True),
        ("refresh", False, True, True),
    ],
)
def test_build_modes(run_wrapper, mode, image_exists, should_build, refresh):
    result, calls = run_wrapper(mode, image_exists=image_exists)

    assert result.returncode == 0, result.stderr
    builds = [args for args in calls if args[0] == "build"]
    assert len(builds) == int(should_build)
    if builds:
        assert ("--pull" in builds[0]) is refresh
        assert ("--no-cache" in builds[0]) is refresh
        assert builds[0][builds[0].index("--platform") + 1] == "linux/amd64"
    assert calls[-1][0] == "run"
    assert calls[-1][-2:] == ["node", "--version"]


def test_failed_refresh_does_not_run_stale_image(run_wrapper):
    result, calls = run_wrapper("refresh", build_exit=17)

    assert result.returncode == 17
    assert calls[-1][0] == "build"
    assert not any(args[0] == "run" for args in calls)


def test_invalid_build_mode(run_wrapper):
    result, calls = run_wrapper("invalid")

    assert result.returncode == 2
    assert "refresh" in result.stderr
    assert calls == []
