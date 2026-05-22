"""Helpers for building and validating registry-archive.json."""

import copy
import json
from pathlib import Path

from registry_utils import normalize_version

ARCHIVE_VERSION = "1.0.0"


def version_sort_key(version: str) -> tuple[int, ...]:
    """Return a sortable key for numeric dotted versions."""
    normalized = normalize_version(version)
    parts = normalized.split(".")
    if not all(part.isdigit() for part in parts):
        raise ValueError(f"Unsupported version format: {version}")
    return tuple(int(part) for part in parts)


def strip_icon(agent: dict) -> dict:
    """Return a historical entry without the shared icon."""
    return {key: value for key, value in agent.items() if key != "icon"}


def _merge_agent_into_archive(archive_by_id: dict[str, dict], agent: dict) -> None:
    """Merge a single agent entry into the archive index."""
    if not isinstance(agent, dict):
        raise ValueError("Archive agent entry must be an object")

    agent_id = agent.get("id")
    version = agent.get("version")
    icon = agent.get("icon")

    if not isinstance(agent_id, str) or not agent_id:
        raise ValueError("Archive agent entry is missing id")
    if not isinstance(version, str) or not version:
        raise ValueError(f"Archive agent {agent_id} is missing version")
    if icon is not None and (not isinstance(icon, str) or not icon):
        raise ValueError(f"Archive agent {agent_id} has an invalid icon value")

    archived_agent = archive_by_id.setdefault(
        agent_id,
        {
            "id": agent_id,
            "icon": None,
            "versions": {},
        },
    )
    if isinstance(icon, str) and icon:
        archived_agent["icon"] = icon
    archived_agent["versions"][version] = strip_icon(agent)


def _finalize_archive(archive_by_id: dict[str, dict]) -> dict:
    """Convert the mutable archive index into the published JSON shape."""
    archived_agents = []
    for agent_id, archived_agent in sorted(archive_by_id.items()):
        versions = list(archived_agent["versions"].values())
        versions.sort(key=lambda entry: version_sort_key(entry["version"]))
        archived_entry = {
            "id": agent_id,
            "versions": versions,
        }
        if isinstance(archived_agent["icon"], str) and archived_agent["icon"]:
            archived_entry["icon"] = archived_agent["icon"]
        archived_agents.append(archived_entry)

    return {"version": ARCHIVE_VERSION, "agents": archived_agents}


def build_archive_from_snapshots(snapshots: list[dict]) -> dict:
    """Merge historical registry snapshots into registry-archive.json format."""
    archive_by_id: dict[str, dict] = {}

    for snapshot in snapshots:
        agents = snapshot.get("agents")
        if not isinstance(agents, list):
            raise ValueError("Snapshot is missing an agents list")
        for agent in agents:
            _merge_agent_into_archive(archive_by_id, agent)

    return _finalize_archive(archive_by_id)


def build_registry_archive(
    current_agents: list[dict], previous_archive: dict | None = None
) -> dict:
    """Merge the current registry snapshot into a previous registry archive."""
    archive_by_id: dict[str, dict] = {}

    if previous_archive is not None:
        errors = validate_registry_archive(previous_archive)
        if errors:
            raise ValueError(
                "Invalid previous archive:\n" + "\n".join(f"- {error}" for error in errors)
            )

        for archived_agent in previous_archive["agents"]:
            agent_id = archived_agent["id"]
            icon = archived_agent.get("icon")
            if icon is not None and (not isinstance(icon, str) or not icon):
                raise ValueError(f"Archived agent {agent_id} has an invalid icon value")

            archive_by_id[agent_id] = {
                "id": agent_id,
                "icon": copy.deepcopy(icon) if icon is not None else None,
                "versions": {
                    entry["version"]: copy.deepcopy(entry) for entry in archived_agent["versions"]
                },
            }

    for agent in current_agents:
        _merge_agent_into_archive(archive_by_id, agent)

    return _finalize_archive(archive_by_id)


def validate_registry_archive(archive: dict) -> list[str]:
    """Validate registry-archive.json structure and invariants."""
    errors = []

    if not isinstance(archive, dict):
        return ["Archive root must be an object"]

    version = archive.get("version")
    if not isinstance(version, str) or not version:
        errors.append("Archive root is missing version")

    agents = archive.get("agents")
    if not isinstance(agents, list):
        return errors + ["Archive root is missing agents list"]

    seen_ids = set()
    for agent in agents:
        if not isinstance(agent, dict):
            errors.append("Archived agent must be an object")
            continue

        agent_id = agent.get("id")
        if not isinstance(agent_id, str) or not agent_id:
            errors.append("Archived agent is missing id")
            continue
        if agent_id in seen_ids:
            errors.append(f"Duplicate archived agent id: {agent_id}")
        seen_ids.add(agent_id)

        icon = agent.get("icon")
        if icon is not None and (not isinstance(icon, str) or not icon):
            errors.append(f"Archived agent {agent_id} has an invalid icon value")

        versions = agent.get("versions")
        if not isinstance(versions, list) or not versions:
            errors.append(f"Archived agent {agent_id} must have a non-empty versions list")
            continue

        seen_versions = set()
        previous_key = None
        for entry in versions:
            if not isinstance(entry, dict):
                errors.append(f"Archived agent {agent_id} has a non-object version entry")
                continue

            entry_id = entry.get("id")
            if entry_id != agent_id:
                errors.append(f"Archived version for {agent_id} has mismatched id: {entry_id}")

            entry_version = entry.get("version")
            if not isinstance(entry_version, str) or not entry_version:
                errors.append(f"Archived agent {agent_id} has a version entry without version")
                continue

            if entry_version in seen_versions:
                errors.append(f"Archived agent {agent_id} has duplicate version {entry_version}")
            seen_versions.add(entry_version)

            key = version_sort_key(entry_version)
            if previous_key is not None and key < previous_key:
                errors.append(f"Archived agent {agent_id} versions are not sorted")
            previous_key = key

    return errors


def validate_registry_archive_sync(current_agents: list[dict], archive: dict) -> list[str]:
    """Validate that the current registry snapshot is represented exactly in the archive."""
    errors = []

    archive_errors = validate_registry_archive(archive)
    if archive_errors:
        return archive_errors

    archive_by_id = {agent["id"]: agent for agent in archive["agents"]}

    for agent in current_agents:
        agent_id = agent["id"]
        agent_version = agent["version"]
        archived_agent = archive_by_id.get(agent_id)

        if archived_agent is None:
            errors.append(f"Current agent {agent_id} is missing from registry-archive.json")
            continue

        current_icon = agent.get("icon")
        archive_icon = archived_agent.get("icon")
        if current_icon != archive_icon:
            errors.append(f"Current agent {agent_id} icon does not match registry-archive.json")

        archived_entry = next(
            (entry for entry in archived_agent["versions"] if entry["version"] == agent_version),
            None,
        )
        if archived_entry is None:
            errors.append(
                f"Current agent {agent_id} version {agent_version} is missing from "
                f"registry-archive.json"
            )
            continue

        if strip_icon(agent) != archived_entry:
            errors.append(
                f"Current agent {agent_id} version {agent_version} differs from "
                f"registry-archive.json"
            )

    return errors


def load_registry_archive(path: Path | None) -> dict | None:
    """Load and validate a registry archive file if it exists."""
    if path is None or not path.exists():
        return None

    archive = json.loads(path.read_text())
    errors = validate_registry_archive(archive)
    if errors:
        raise ValueError(
            f"Invalid registry archive at {path}:\n" + "\n".join(f"- {error}" for error in errors)
        )
    return archive
