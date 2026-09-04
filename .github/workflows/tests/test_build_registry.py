"""Tests for build_registry icon validation and dry-run."""

import json
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from build_registry import (
    HAS_JSONSCHEMA,
    build_registry,
    is_public_https_url,
    url_exists,
    validate_icon,
    validate_icon_monochrome,
    validate_preview,
)
from registry_utils import semver_sort_key

requires_jsonschema = pytest.mark.skipif(
    not HAS_JSONSCHEMA, reason="schema-only rule needs jsonschema installed"
)


def socket_result(ip: str):
    return [(None, None, None, None, (ip, 443))]


class StubResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class TestUrlSafety:
    def test_rejects_non_https_urls(self, monkeypatch):
        monkeypatch.setattr("build_registry.socket.getaddrinfo", lambda *args, **kwargs: [])

        assert not is_public_https_url("http://example.com/archive.tar.gz")

    def test_rejects_private_addresses(self, monkeypatch):
        monkeypatch.setattr(
            "build_registry.socket.getaddrinfo",
            lambda *args, **kwargs: socket_result("127.0.0.1"),
        )

        assert not is_public_https_url("https://example.com/archive.tar.gz")

    def test_rejects_shared_address_space(self, monkeypatch):
        monkeypatch.setattr(
            "build_registry.socket.getaddrinfo",
            lambda *args, **kwargs: socket_result("100.64.0.1"),
        )

        assert not is_public_https_url("https://example.com/archive.tar.gz")

    def test_accepts_public_https_addresses(self, monkeypatch):
        monkeypatch.setattr(
            "build_registry.socket.getaddrinfo",
            lambda *args, **kwargs: socket_result("93.184.216.34"),
        )

        assert is_public_https_url("https://example.com/archive.tar.gz")

    def test_url_exists_retries_transient_dns_failure(self, monkeypatch):
        calls = 0

        def fake_getaddrinfo(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("temporary resolver failure")
            return socket_result("93.184.216.34")

        monkeypatch.setattr("build_registry.socket.getaddrinfo", fake_getaddrinfo)
        monkeypatch.setattr(
            "build_registry.URL_OPENER.open",
            lambda *args, **kwargs: StubResponse(),
        )
        monkeypatch.setattr("time.sleep", lambda *args, **kwargs: None)

        assert url_exists("https://example.com/archive.tar.gz")
        assert calls == 2


# --- validate_icon_monochrome ---


class TestValidateIconMonochrome:
    def _root(self, svg: str) -> ET.Element:
        return ET.fromstring(svg)

    def test_valid_fill_current_color(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<path fill="currentColor" d="M0 0h16v16H0z"/>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []

    def test_valid_stroke_current_color(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<line stroke="currentColor" x1="0" y1="0" x2="16" y2="16"/>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []

    def test_valid_fill_on_svg_root(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg" fill="currentColor">'
            '<path d="M0 0h16v16H0z"/>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []

    def test_valid_fill_none_with_stroke_current_color(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<circle fill="none" stroke="currentColor" cx="8" cy="8" r="7"/>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []

    def test_hardcoded_hex_fill(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg"><path fill="#FF0000" d="M0 0h16v16H0z"/></svg>'
        )
        errors = validate_icon_monochrome(root)
        assert any("hardcoded fill" in e for e in errors)
        assert any("must use currentColor" in e for e in errors)

    def test_hardcoded_named_color(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<rect fill="red" width="16" height="16"/>'
            "</svg>"
        )
        errors = validate_icon_monochrome(root)
        assert any('fill="red"' in e for e in errors)

    def test_hardcoded_stroke_color(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<line stroke="#000" x1="0" y1="0" x2="16" y2="16"/>'
            "</svg>"
        )
        errors = validate_icon_monochrome(root)
        assert any("hardcoded stroke" in e for e in errors)

    def test_no_fill_or_stroke_at_all(self):
        root = self._root('<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h16v16H0z"/></svg>')
        errors = validate_icon_monochrome(root)
        assert errors == ["Icon must use currentColor for fills/strokes to support theming"]

    def test_inline_style_hardcoded(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<path style="fill: #123456" d="M0 0h16v16H0z"/>'
            "</svg>"
        )
        errors = validate_icon_monochrome(root)
        assert any("hardcoded style fill" in e for e in errors)

    def test_inline_style_current_color(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<path style="fill: currentColor" d="M0 0h16v16H0z"/>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []

    def test_style_element_hardcoded(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            "<style>.a { fill: #FF0000; }</style>"
            '<path class="a" d="M0 0h16v16H0z"/>'
            "</svg>"
        )
        errors = validate_icon_monochrome(root)
        assert any("hardcoded CSS fill" in e for e in errors)

    def test_style_element_current_color(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            "<style>.a { fill: currentColor; }</style>"
            '<path class="a" d="M0 0h16v16H0z"/>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []

    def test_mixed_elements_with_fill_none(self):
        """codex-acp style: fill on root, stroke on children, fill=none on some."""
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg" fill="currentColor">'
            '<path d="M0 0h16v16H0z" fill-rule="nonzero"/>'
            '<circle cx="8" cy="8" r="3"/>'
            '<rect stroke="currentColor" fill="none" x="2" y="2" width="12" height="12"/>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []

    def test_inherit_fill_is_allowed(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg" fill="currentColor">'
            '<g fill="inherit"><path d="M0 0z"/></g>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []


# --- validate_icon ---


class TestValidateIcon:
    def _write_icon(self, tmpdir: Path, content: str) -> Path:
        p = tmpdir / "icon.svg"
        p.write_text(content)
        return p

    def test_valid_16x16(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(
                Path(d),
                '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
                '<path fill="currentColor" d="M0 0z"/>'
                "</svg>",
            )
            assert validate_icon(p) == []

    def test_valid_viewbox_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(
                Path(d),
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
                '<path fill="currentColor" d="M0 0z"/>'
                "</svg>",
            )
            assert validate_icon(p) == []

    def test_non_square(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(
                Path(d),
                '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="32">'
                '<path fill="currentColor" d="M0 0z"/>'
                "</svg>",
            )
            errors = validate_icon(p)
            assert any("square" in e for e in errors)

    def test_wrong_size(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(
                Path(d),
                '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">'
                '<path fill="currentColor" d="M0 0z"/>'
                "</svg>",
            )
            errors = validate_icon(p)
            assert any("16x16" in e for e in errors)

    def test_missing_dimensions(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(
                Path(d),
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<path fill="currentColor" d="M0 0z"/>'
                "</svg>",
            )
            errors = validate_icon(p)
            assert any("missing width/height" in e.lower() for e in errors)

    def test_invalid_xml(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(Path(d), "<not-closed>")
            errors = validate_icon(p)
            assert any("not valid SVG/XML" in e for e in errors)

    def test_non_svg_root(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(Path(d), "<div>hello</div>")
            errors = validate_icon(p)
            assert any("<svg>" in e for e in errors)

    def test_missing_file(self):
        errors = validate_icon(Path("/nonexistent/icon.svg"))
        assert any("Cannot read icon" in e for e in errors)

    def test_width_with_px_unit(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(
                Path(d),
                '<svg xmlns="http://www.w3.org/2000/svg" width="16px" height="16px">'
                '<path fill="currentColor" d="M0 0z"/>'
                "</svg>",
            )
            assert validate_icon(p) == []

    def test_html_comments_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(
                Path(d),
                '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
                "<!-- a comment -->"
                '<path fill="currentColor" d="M0 0z"/>'
                "</svg>",
            )
            errors = validate_icon(p)
            assert any("HTML comments" in e for e in errors)


# --- preview channel ---

REPO_ROOT = Path(__file__).resolve().parents[3]
VALID_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
    '<path fill="currentColor" d="M0 0z"/>'
    "</svg>"
)


def npx_preview(agent_id: str, version: str) -> dict:
    return {
        "version": version,
        "distribution": {"npx": {"package": f"@acp/{agent_id}@{version}"}},
    }


def agent_manifest(agent_id: str, version: str, preview: dict | None = None, **extra) -> dict:
    manifest = {
        "id": agent_id,
        "name": agent_id,
        "version": version,
        "description": f"{agent_id} test agent",
        "distribution": {"npx": {"package": f"@acp/{agent_id}@{version}"}},
    }
    manifest.update(extra)
    if preview is not None:
        manifest["preview"] = preview
    return manifest


def write_registry(root: Path, manifests: list[dict]) -> Path:
    shutil.copy(REPO_ROOT / "agent.schema.json", root / "agent.schema.json")
    for manifest in manifests:
        entry_dir = root / manifest["id"]
        entry_dir.mkdir(parents=True, exist_ok=True)
        (entry_dir / "agent.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (entry_dir / "icon.svg").write_text(VALID_ICON)
    return root


def read_registries(root: Path) -> dict[str, dict]:
    return {
        name: json.loads((root / "dist" / f"{name}.json").read_text())
        for name in ("registry", "registry-for-jetbrains", "registry-for-jetbrains-preview")
    }


def by_id(registry: dict) -> dict[str, dict]:
    return {agent["id"]: agent for agent in registry["agents"]}


@pytest.fixture(autouse=True)
def _skip_url_validation(monkeypatch):
    monkeypatch.setattr("build_registry.SKIP_URL_VALIDATION", True)


class TestValidatePreview:
    def test_no_preview_block(self):
        assert validate_preview(agent_manifest("agent-a", "1.8.0")) == []

    def test_valid_preview_block(self):
        agent = agent_manifest("agent-a", "1.8.0", npx_preview("agent-a", "1.9.0-preview.1"))

        assert validate_preview(agent) == []

    def test_plain_release_preview_version(self):
        agent = agent_manifest("agent-a", "1.8.0", npx_preview("agent-a", "1.9.1"))

        assert validate_preview(agent) == []

    @pytest.mark.parametrize(
        "version",
        ["1.9-preview.1", "1.9.0-preview", "1.9.0-rc.1", "1.9.0+preview.1", "latest"],
    )
    def test_malformed_preview_version(self, version):
        agent = agent_manifest("agent-a", "1.8.0", npx_preview("agent-a", version))

        errors = validate_preview(agent)

        assert any("preview.version" in e for e in errors)

    def test_package_spec_disagreeing_with_preview_version(self):
        agent = agent_manifest(
            "agent-a",
            "1.8.0",
            {
                "version": "1.9.0-preview.2",
                "distribution": {"npx": {"package": "@acp/agent-a@1.9.0-preview.1"}},
            },
        )

        errors = validate_preview(agent)

        assert any("doesn't match" in e for e in errors)

    def test_empty_preview_distribution(self):
        agent = agent_manifest(
            "agent-a", "1.8.0", {"version": "1.9.0-preview.1", "distribution": {}}
        )

        errors = validate_preview(agent)

        assert any("preview.distribution" in e for e in errors)

    def test_uvx_preview_spec_matching_preview_version(self):
        agent = agent_manifest(
            "agent-a",
            "1.8.0",
            {
                "version": "1.9.0-preview.1",
                "distribution": {"uvx": {"package": "acp-agent-a==1.9.0-preview.1"}},
            },
        )

        assert validate_preview(agent) == []

    def test_no_ordering_constraint_against_stable(self):
        agent = agent_manifest("agent-a", "1.9.1", npx_preview("agent-a", "1.9.0-preview.1"))

        assert validate_preview(agent) == []


class TestPreviewRegistryOutputs:
    def test_writes_three_registries(self, tmp_path):
        write_registry(
            tmp_path,
            [
                agent_manifest("agent-a", "1.8.0", npx_preview("agent-a", "1.9.0-preview.2")),
                agent_manifest("agent-b", "2.0.0"),
            ],
        )

        build_registry(registry_dir=tmp_path)

        registries = read_registries(tmp_path)
        assert set(registries) == {
            "registry",
            "registry-for-jetbrains",
            "registry-for-jetbrains-preview",
        }

    def test_public_registries_hide_the_preview_channel(self, tmp_path):
        write_registry(
            tmp_path,
            [agent_manifest("agent-a", "1.8.0", npx_preview("agent-a", "1.9.0-preview.2"))],
        )

        build_registry(registry_dir=tmp_path)
        registries = read_registries(tmp_path)

        for name in ("registry", "registry-for-jetbrains"):
            entry = by_id(registries[name])["agent-a"]
            assert "preview" not in entry
            assert entry["version"] == "1.8.0"
            assert entry["distribution"]["npx"]["package"] == "@acp/agent-a@1.8.0"

    def test_preview_registry_substitutes_version_and_distribution(self, tmp_path):
        write_registry(
            tmp_path,
            [
                agent_manifest(
                    "agent-a",
                    "1.8.0",
                    npx_preview("agent-a", "1.9.0-preview.2"),
                    repository="https://github.com/acp/agent-a",
                    authors=["ACP"],
                    license="proprietary",
                )
            ],
        )

        build_registry(registry_dir=tmp_path)
        registries = read_registries(tmp_path)

        stable = by_id(registries["registry-for-jetbrains"])["agent-a"]
        preview = by_id(registries["registry-for-jetbrains-preview"])["agent-a"]

        assert "preview" not in preview
        assert preview["version"] == "1.9.0-preview.2"
        assert preview["distribution"]["npx"]["package"] == "@acp/agent-a@1.9.0-preview.2"
        for field in ("id", "name", "description", "repository", "authors", "license", "icon"):
            assert preview[field] == stable[field]

    def test_agent_without_preview_block_uses_stable_entry(self, tmp_path):
        write_registry(tmp_path, [agent_manifest("agent-b", "2.0.0")])

        build_registry(registry_dir=tmp_path)
        registries = read_registries(tmp_path)

        assert (
            by_id(registries["registry-for-jetbrains-preview"])["agent-b"]
            == by_id(registries["registry-for-jetbrains"])["agent-b"]
        )

    def test_stable_ahead_of_preview_line_serves_stable(self, tmp_path):
        write_registry(
            tmp_path,
            [agent_manifest("agent-a", "1.9.1", npx_preview("agent-a", "1.9.0-preview.1"))],
        )

        build_registry(registry_dir=tmp_path)
        registries = read_registries(tmp_path)

        entry = by_id(registries["registry-for-jetbrains-preview"])["agent-a"]
        assert entry["version"] == "1.9.1"
        assert entry["distribution"]["npx"]["package"] == "@acp/agent-a@1.9.1"
        assert "preview" not in entry

    def test_preview_version_never_below_stable(self, tmp_path):
        write_registry(
            tmp_path,
            [
                agent_manifest("agent-a", "1.8.0", npx_preview("agent-a", "1.9.0-preview.2")),
                agent_manifest("agent-b", "2.0.0"),
                agent_manifest("agent-c", "1.9.1", npx_preview("agent-c", "1.9.0-preview.1")),
                agent_manifest("agent-d", "1.9.0", npx_preview("agent-d", "1.9.1")),
            ],
        )

        build_registry(registry_dir=tmp_path)
        registries = read_registries(tmp_path)

        stable = by_id(registries["registry-for-jetbrains"])
        preview = by_id(registries["registry-for-jetbrains-preview"])
        assert set(stable) == set(preview)
        for agent_id, entry in preview.items():
            assert semver_sort_key(entry["version"]) >= semver_sort_key(stable[agent_id]["version"])

    def test_jetbrains_patches_apply_to_the_preview_registry(self, tmp_path):
        write_registry(
            tmp_path,
            [
                agent_manifest(
                    "claude-acp", "0.73.0", npx_preview("claude-acp", "0.74.0-preview.1")
                ),
                agent_manifest("github-copilot-cli", "1.0.0"),
                agent_manifest("github-copilot", "1.0.0"),
            ],
        )

        build_registry(registry_dir=tmp_path)
        registries = read_registries(tmp_path)

        preview_agents = by_id(registries["registry-for-jetbrains-preview"])
        claude = preview_agents["claude-acp"]
        assert claude["bundled"] is True
        assert "--hide-claude-auth" in claude["distribution"]["npx"]["args"]
        assert claude["version"] == "0.74.0-preview.1"
        assert "github-copilot-cli" not in preview_agents
        assert "github-copilot" in preview_agents
        assert "github-copilot" not in by_id(registries["registry"])

    def test_preview_may_declare_a_distribution_type_the_base_entry_lacks(self, tmp_path):
        write_registry(
            tmp_path,
            [
                agent_manifest(
                    "agent-a",
                    "1.8.0",
                    {
                        "version": "1.9.0-preview.1",
                        "distribution": {"uvx": {"package": "acp-agent-a==1.9.0-preview.1"}},
                    },
                )
            ],
        )

        build_registry(registry_dir=tmp_path)
        registries = read_registries(tmp_path)

        entry = by_id(registries["registry-for-jetbrains-preview"])["agent-a"]
        assert entry["distribution"] == {"uvx": {"package": "acp-agent-a==1.9.0-preview.1"}}

    def test_no_network_probe_for_preview_artifacts(self, tmp_path, monkeypatch):
        monkeypatch.setattr("build_registry.SKIP_URL_VALIDATION", False)
        probed: list[str] = []

        def record(url, *args, **kwargs):
            probed.append(url)
            return True

        monkeypatch.setattr("build_registry.url_exists", record)
        write_registry(
            tmp_path,
            [agent_manifest("agent-a", "1.8.0", npx_preview("agent-a", "1.9.0-preview.2"))],
        )

        build_registry(registry_dir=tmp_path)

        assert probed == ["https://registry.npmjs.org/@acp/agent-a"]


class TestPreviewValidationFailures:
    def _build_fails(self, tmp_path, manifest) -> None:
        write_registry(tmp_path, [manifest])
        with pytest.raises(SystemExit) as excinfo:
            build_registry(registry_dir=tmp_path)
        assert excinfo.value.code == 1

    @requires_jsonschema
    def test_extra_key_in_preview_block(self, tmp_path):
        preview = npx_preview("agent-a", "1.9.0-preview.1")
        preview["name"] = "Agent A Preview"

        self._build_fails(tmp_path, agent_manifest("agent-a", "1.8.0", preview))

    def test_preview_without_distribution(self, tmp_path):
        self._build_fails(
            tmp_path, agent_manifest("agent-a", "1.8.0", {"version": "1.9.0-preview.1"})
        )

    def test_empty_preview_distribution(self, tmp_path):
        self._build_fails(
            tmp_path,
            agent_manifest("agent-a", "1.8.0", {"version": "1.9.0-preview.1", "distribution": {}}),
        )

    @requires_jsonschema
    def test_binary_preview_distribution(self, tmp_path):
        self._build_fails(
            tmp_path,
            agent_manifest(
                "agent-a",
                "1.8.0",
                {
                    "version": "1.9.0-preview.1",
                    "distribution": {
                        "darwin-aarch64": {
                            "archive": "https://example.com/a-1.9.0-preview.1.tar.gz",
                            "cmd": "agent-a",
                        }
                    },
                },
            ),
        )

    def test_preview_package_spec_version_mismatch(self, tmp_path):
        self._build_fails(
            tmp_path,
            agent_manifest(
                "agent-a",
                "1.8.0",
                {
                    "version": "1.9.0-preview.2",
                    "distribution": {"npx": {"package": "@acp/agent-a@1.9.0-preview.1"}},
                },
            ),
        )

    def test_prerelease_in_root_version(self, tmp_path):
        self._build_fails(tmp_path, agent_manifest("agent-a", "1.9.0-preview.1"))
