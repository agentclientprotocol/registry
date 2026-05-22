"""Tests for registry archive backfill logic."""

from backfill_registry_archive import find_registry_asset_url
from registry_archive import (
    build_archive_from_snapshots,
    build_registry_archive,
    validate_registry_archive,
    validate_registry_archive_sync,
)


class TestFindRegistryAssetUrl:
    def test_returns_registry_asset_download_url(self):
        release = {
            "assets": [
                {"name": "agent.schema.json", "browser_download_url": "https://example/schema"},
                {"name": "registry.json", "browser_download_url": "https://example/registry"},
            ]
        }

        assert find_registry_asset_url(release) == "https://example/registry"

    def test_returns_none_when_registry_asset_is_absent(self):
        release = {"assets": [{"name": "agent.schema.json", "browser_download_url": "x"}]}

        assert find_registry_asset_url(release) is None


class TestBuildArchiveFromSnapshots:
    def test_groups_entries_by_agent_and_sorts_versions(self):
        snapshots = [
            {
                "agents": [
                    {
                        "id": "codex-acp",
                        "name": "Codex CLI",
                        "version": "0.10.0",
                        "description": "desc",
                        "icon": "https://cdn.example/codex.svg",
                        "distribution": {"npx": {"package": "@zed/codex@0.10.0"}},
                    },
                    {
                        "id": "claude-acp",
                        "name": "Claude",
                        "version": "0.29.0",
                        "description": "desc",
                        "icon": "https://cdn.example/claude.svg",
                        "distribution": {"npx": {"package": "@anthropic/claude@0.29.0"}},
                    },
                ]
            },
            {
                "agents": [
                    {
                        "id": "codex-acp",
                        "name": "Codex CLI",
                        "version": "0.9.2",
                        "description": "desc",
                        "icon": "https://cdn.example/codex-old.svg",
                        "distribution": {
                            "binary": {"darwin-aarch64": {"archive": "a", "cmd": "b"}}
                        },
                    },
                    {
                        "id": "codex-acp",
                        "name": "Codex CLI",
                        "version": "0.11.1",
                        "description": "desc",
                        "icon": "https://cdn.example/codex-new.svg",
                        "distribution": {
                            "binary": {"darwin-aarch64": {"archive": "c", "cmd": "d"}}
                        },
                    },
                ]
            },
        ]

        archive = build_archive_from_snapshots(snapshots)

        assert archive["version"] == "1.0.0"
        assert [agent["id"] for agent in archive["agents"]] == ["claude-acp", "codex-acp"]

        codex = archive["agents"][1]
        assert codex["icon"] == "https://cdn.example/codex-new.svg"
        assert [entry["version"] for entry in codex["versions"]] == ["0.9.2", "0.10.0", "0.11.1"]
        assert all("icon" not in entry for entry in codex["versions"])

    def test_replaces_duplicate_version_with_latest_published_entry(self):
        snapshots = [
            {
                "agents": [
                    {
                        "id": "codex-acp",
                        "name": "Codex CLI",
                        "version": "0.9.3",
                        "description": "old",
                        "icon": "https://cdn.example/codex.svg",
                        "distribution": {
                            "binary": {"darwin-aarch64": {"archive": "old", "cmd": "b"}}
                        },
                    }
                ]
            },
            {
                "agents": [
                    {
                        "id": "codex-acp",
                        "name": "Codex CLI",
                        "version": "0.9.3",
                        "description": "new",
                        "icon": "https://cdn.example/codex.svg",
                        "distribution": {"npx": {"package": "@zed/codex@0.9.3"}},
                    }
                ]
            },
        ]

        archive = build_archive_from_snapshots(snapshots)

        codex_versions = archive["agents"][0]["versions"]
        assert len(codex_versions) == 1
        assert codex_versions[0]["description"] == "new"
        assert codex_versions[0]["distribution"] == {"npx": {"package": "@zed/codex@0.9.3"}}

    def test_preserves_agent_when_some_snapshots_omit_icon(self):
        snapshots = [
            {
                "agents": [
                    {
                        "id": "minion-code",
                        "name": "Minion Code",
                        "version": "0.1.43",
                        "description": "desc",
                        "distribution": {"uvx": {"package": "minion-code@0.1.43"}},
                    }
                ]
            },
            {
                "agents": [
                    {
                        "id": "minion-code",
                        "name": "Minion Code",
                        "version": "0.1.44",
                        "description": "desc",
                        "icon": "https://cdn.example/minion-code.svg",
                        "distribution": {"uvx": {"package": "minion-code@0.1.44"}},
                    }
                ]
            },
        ]

        archive = build_archive_from_snapshots(snapshots)

        minion = archive["agents"][0]
        assert minion["id"] == "minion-code"
        assert minion["icon"] == "https://cdn.example/minion-code.svg"
        assert [entry["version"] for entry in minion["versions"]] == ["0.1.43", "0.1.44"]


class TestBuildRegistryArchive:
    def test_merges_current_agents_into_previous_archive(self):
        previous_archive = {
            "version": "1.0.0",
            "agents": [
                {
                    "id": "codex-acp",
                    "icon": "https://cdn.example/codex-old.svg",
                    "versions": [
                        {
                            "id": "codex-acp",
                            "name": "Codex CLI",
                            "version": "0.9.2",
                            "description": "desc",
                            "distribution": {
                                "binary": {"darwin-aarch64": {"archive": "a", "cmd": "b"}}
                            },
                        }
                    ],
                }
            ],
        }
        current_agents = [
            {
                "id": "codex-acp",
                "name": "Codex CLI",
                "version": "0.11.1",
                "description": "desc",
                "icon": "https://cdn.example/codex-new.svg",
                "distribution": {"npx": {"package": "@zed/codex@0.11.1"}},
            },
            {
                "id": "claude-acp",
                "name": "Claude",
                "version": "0.30.0",
                "description": "desc",
                "icon": "https://cdn.example/claude.svg",
                "distribution": {"npx": {"package": "@anthropic/claude@0.30.0"}},
            },
        ]

        archive = build_registry_archive(current_agents, previous_archive)

        assert [agent["id"] for agent in archive["agents"]] == ["claude-acp", "codex-acp"]
        codex = archive["agents"][1]
        assert codex["icon"] == "https://cdn.example/codex-new.svg"
        assert [entry["version"] for entry in codex["versions"]] == ["0.9.2", "0.11.1"]
        assert all("icon" not in entry for entry in codex["versions"])

    def test_validate_registry_archive_flags_unsorted_versions(self):
        archive = {
            "version": "1.0.0",
            "agents": [
                {
                    "id": "codex-acp",
                    "versions": [
                        {
                            "id": "codex-acp",
                            "name": "Codex CLI",
                            "version": "0.11.1",
                            "description": "desc",
                            "distribution": {"npx": {"package": "@zed/codex@0.11.1"}},
                        },
                        {
                            "id": "codex-acp",
                            "name": "Codex CLI",
                            "version": "0.9.2",
                            "description": "desc",
                            "distribution": {
                                "binary": {"darwin-aarch64": {"archive": "a", "cmd": "b"}}
                            },
                        },
                    ],
                }
            ],
        }

        errors = validate_registry_archive(archive)

        assert errors == ["Archived agent codex-acp versions are not sorted"]

    def test_validate_registry_archive_sync_accepts_matching_current_entry(self):
        current_agents = [
            {
                "id": "codex-acp",
                "name": "Codex CLI",
                "version": "0.11.1",
                "description": "desc",
                "icon": "https://cdn.example/codex.svg",
                "distribution": {"npx": {"package": "@zed/codex@0.11.1"}},
            }
        ]
        archive = {
            "version": "1.0.0",
            "agents": [
                {
                    "id": "codex-acp",
                    "icon": "https://cdn.example/codex.svg",
                    "versions": [
                        {
                            "id": "codex-acp",
                            "name": "Codex CLI",
                            "version": "0.11.1",
                            "description": "desc",
                            "distribution": {"npx": {"package": "@zed/codex@0.11.1"}},
                        }
                    ],
                }
            ],
        }

        assert validate_registry_archive_sync(current_agents, archive) == []

    def test_validate_registry_archive_sync_reports_entry_mismatch(self):
        current_agents = [
            {
                "id": "codex-acp",
                "name": "Codex CLI",
                "version": "0.11.1",
                "description": "new",
                "icon": "https://cdn.example/codex.svg",
                "distribution": {"npx": {"package": "@zed/codex@0.11.1"}},
            }
        ]
        archive = {
            "version": "1.0.0",
            "agents": [
                {
                    "id": "codex-acp",
                    "icon": "https://cdn.example/codex.svg",
                    "versions": [
                        {
                            "id": "codex-acp",
                            "name": "Codex CLI",
                            "version": "0.11.1",
                            "description": "old",
                            "distribution": {"npx": {"package": "@zed/codex@0.11.1"}},
                        }
                    ],
                }
            ],
        }

        assert validate_registry_archive_sync(current_agents, archive) == [
            "Current agent codex-acp version 0.11.1 differs from registry-archive.json"
        ]

    def test_validate_registry_archive_sync_reports_icon_mismatch(self):
        current_agents = [
            {
                "id": "codex-acp",
                "name": "Codex CLI",
                "version": "0.11.1",
                "description": "desc",
                "icon": "https://cdn.example/codex-new.svg",
                "distribution": {"npx": {"package": "@zed/codex@0.11.1"}},
            }
        ]
        archive = {
            "version": "1.0.0",
            "agents": [
                {
                    "id": "codex-acp",
                    "icon": "https://cdn.example/codex-old.svg",
                    "versions": [
                        {
                            "id": "codex-acp",
                            "name": "Codex CLI",
                            "version": "0.11.1",
                            "description": "desc",
                            "distribution": {"npx": {"package": "@zed/codex@0.11.1"}},
                        }
                    ],
                }
            ],
        }

        assert validate_registry_archive_sync(current_agents, archive) == [
            "Current agent codex-acp icon does not match registry-archive.json"
        ]
