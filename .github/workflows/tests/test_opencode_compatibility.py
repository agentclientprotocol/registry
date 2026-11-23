"""Keep saved OpenCode V2 IDs working as the canonical entry advances."""

import copy
import json
import shutil
import sys
from pathlib import Path

import jsonschema
import pytest

import build_registry
import update_versions
from registry_utils import with_compatibility_entries
from verify_agents import load_registry

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRIES = (
    "registry.json",
    "registry-for-jetbrains.json",
    "registry-for-jetbrains-preview.json",
    "registry-for-jetbrains-air.json",
)


@pytest.fixture
def registry(tmp_path, monkeypatch):
    shutil.copytree(REPO_ROOT / "opencode", tmp_path / "opencode")
    shutil.copy(REPO_ROOT / "agent.schema.json", tmp_path / "agent.schema.json")
    monkeypatch.setattr(build_registry, "SKIP_URL_VALIDATION", True)
    return tmp_path


def manifest(root):
    return json.loads((root / "opencode/agent.json").read_text())


def assert_published_compatibility(root):
    schema = json.loads((root / "agent.schema.json").read_text())
    for filename in REGISTRIES:
        data = json.loads((root / "dist" / filename).read_text())
        entries = {entry["id"]: entry for entry in data["agents"]}
        assert len(data["agents"]) == len(entries) == 2
        canonical, legacy = entries["opencode"], entries["opencode-v2"]
        for entry in entries.values():
            jsonschema.validate(entry, schema)
        assert legacy["version"] == canonical["version"] == manifest(root)["version"]
        assert legacy["distribution"] == canonical["distribution"]
        assert legacy["name"] == "OpenCode (legacy ID)"
        assert "Select OpenCode (opencode)" in legacy["description"]
        assert legacy["icon"].endswith("/opencode-v2.svg")
        assert canonical["name"] == "OpenCode"
        assert canonical["description"] == manifest(root)["description"]
    assert (root / "dist/opencode-v2.svg").read_bytes() == (root / "opencode/icon.svg").read_bytes()


def test_all_published_indexes_preserve_legacy_lookup_and_icon(registry):
    build_registry.build_registry(registry_dir=registry)
    assert_published_compatibility(registry)
    assert not (registry / "opencode-v2").exists()


def test_update_once_refreshes_both_ids_on_next_build(registry, monkeypatch):
    entry = manifest(registry)
    major, minor, patch = map(int, entry["version"].split("."))
    newer = f"{major}.{minor}.{patch + 1}"
    monkeypatch.setattr(update_versions, "get_github_release_versions", lambda _: {newer})
    monkeypatch.setattr(
        update_versions,
        "get_github_release_digests",
        lambda *args: {
            target["archive"].rsplit("/", 1)[-1]: "a" * 64
            for target in entry["distribution"]["binary"].values()
        },
    )
    updates = update_versions.find_all_agents(registry)
    assert len(updates) == 1
    path, entry = updates[0]
    update, error = update_versions.check_agent_version(path, entry)
    assert error is None
    assert update.agent_id == "opencode"
    assert update_versions.apply_update(update)
    build_registry.build_registry(registry_dir=registry)
    assert_published_compatibility(registry)
    for published in load_registry(registry):
        assert published["version"] == newer
        for target in published["distribution"]["binary"].values():
            assert f"/v{newer}/" in target["archive"]
            assert target["sha256"] == "a" * 64


def test_auth_and_protocol_matrix_loader_includes_legacy_id(registry):
    entries = {entry["id"]: entry for entry in load_registry(registry)}
    assert entries["opencode-v2"]["distribution"] == entries["opencode"]["distribution"]
    assert entries["opencode-v2"]["version"] == entries["opencode"]["version"]


def test_quarantining_canonical_entry_also_excludes_legacy_id(registry):
    (registry / "quarantine.json").write_text(json.dumps({"opencode": "test failure"}))
    assert load_registry(registry) == []


def test_quarantining_legacy_id_does_not_exclude_canonical_entry(registry):
    (registry / "quarantine.json").write_text(json.dumps({"opencode-v2": "test failure"}))
    assert [entry["id"] for entry in load_registry(registry)] == ["opencode"]


def test_scoped_build_accepts_legacy_id(registry, capsys):
    build_registry.build_registry(registry_dir=registry, agent_ids={"opencode-v2"})
    assert "validated 2 agents successfully" in capsys.readouterr().out
    assert not (registry / "dist").exists()


def test_scoped_build_rejects_missing_canonical_entry(tmp_path):
    with pytest.raises(SystemExit, match="1"):
        build_registry.build_registry(registry_dir=tmp_path, agent_ids={"opencode-v2"})


def test_version_cli_accepts_legacy_id_and_updates_only_canonical(registry, monkeypatch, capsys):
    entry = manifest(registry)
    monkeypatch.setattr(
        update_versions, "find_all_agents", lambda _: [(registry / "opencode/agent.json", entry)]
    )
    monkeypatch.setattr(
        update_versions, "get_github_release_versions", lambda _: {entry["version"]}
    )
    monkeypatch.setattr(sys, "argv", ["update_versions.py", "--agents", "opencode-v2", "--json"])
    with pytest.raises(SystemExit, match="0"):
        update_versions.main()
    result = json.loads(capsys.readouterr().out)
    assert result == {"updates": [], "errors": [], "up_to_date": ["opencode"]}


def test_compatibility_entry_is_independent_and_preserves_all_launch_fields(registry):
    canonical = manifest(registry)
    canonical["distribution"]["binary"]["windows-aarch64"]["env"] = {"TEST_SETTING": "value"}
    before = copy.deepcopy(canonical)
    entries = with_compatibility_entries([canonical])
    assert canonical == before
    legacy = next(entry for entry in entries if entry["id"] == "opencode-v2")
    assert legacy["distribution"] == canonical["distribution"]
    legacy["distribution"]["binary"].clear()
    assert canonical == before


def test_reintroduced_legacy_manifest_fails_build(registry):
    shutil.copytree(registry / "opencode", registry / "opencode-v2")
    entry = manifest(registry)
    entry["id"] = "opencode-v2"
    (registry / "opencode-v2/agent.json").write_text(json.dumps(entry))
    with pytest.raises(SystemExit, match="1"):
        build_registry.build_registry(registry_dir=registry)
    assert not (registry / "dist").exists()
