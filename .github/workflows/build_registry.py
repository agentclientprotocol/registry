#!/usr/bin/env python3
"""Build aggregated registry.json from individual agent directories."""

import argparse
import copy
import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from registry_utils import (
    extract_npm_package_name,
    extract_npm_package_version,
    extract_pypi_package_name,
    normalize_version,
    should_skip_dir,
)

try:
    import jsonschema

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

REGISTRY_VERSION = "1.0.0"
REQUIRED_FIELDS = {"id", "name", "version", "description", "distribution"}
VALID_DISTRIBUTION_TYPES = {"binary", "npx", "uvx"}
VALID_PLATFORMS = {
    "darwin-aarch64",
    "darwin-x86_64",
    "linux-aarch64",
    "linux-x86_64",
    "windows-aarch64",
    "windows-x86_64",
}
REQUIRED_OS_FAMILIES = {"darwin", "linux", "windows"}
REJECTED_ARCHIVE_EXTENSIONS = (".dmg", ".pkg", ".deb", ".rpm", ".msi", ".appimage")

# Can be overridden via environment variable
DEFAULT_BASE_URL = "https://cdn.agentclientprotocol.com/registry/v1/latest"

# Icon requirements
PREFERRED_ICON_SIZE = 16
ALLOWED_FILL_STROKE_VALUES = {"currentcolor", "none", "inherit"}

# URL validation
SKIP_URL_VALIDATION = os.environ.get("SKIP_URL_VALIDATION", "").lower() in (
    "1",
    "true",
    "yes",
)


def url_exists(url: str, method: str = "HEAD", retries: int = 3) -> bool:
    """Check if a URL exists using HEAD or GET request with retries."""
    import time

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, method=method)
            req.add_header("User-Agent", "ACP-Registry-Validator/1.0")
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.status in (200, 301, 302)
        except urllib.error.HTTPError as e:
            # Some servers don't support HEAD, try GET
            if method == "HEAD" and e.code in (403, 405):
                return url_exists(url, method="GET", retries=retries - attempt)
            if attempt < retries - 1 and e.code in (429, 500, 502, 503, 504):
                time.sleep(2**attempt)
                continue
            return False
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt < retries - 1:
                time.sleep(2**attempt)
                continue
            return False
    return False


def extract_version_from_url(url: str) -> str | None:
    """Extract version from binary archive URL."""
    # GitHub releases: /download/v1.0.0/ or /releases/v1.0.0/
    github_match = re.search(r"/(?:download|releases)/v?([\d.]+)/", url)
    if github_match:
        return normalize_version(github_match.group(1))
    # npm tarballs: /-/package-1.0.0.tgz
    npm_match = re.search(r"/-/[^/]+-(\d+\.\d+\.\d+)\.tgz", url)
    if npm_match:
        return npm_match.group(1)
    return None


def validate_distribution_versions(agent_version: str, distribution: dict) -> list[str]:
    """Validate that distribution versions match agent version and don't use 'latest'."""
    errors = []

    # Check binary URLs for /latest/ and version mismatches
    if "binary" in distribution:
        for platform, target in distribution["binary"].items():
            url = target.get("archive", "")
            if "/latest/" in url:
                errors.append(
                    f"Binary URL for {platform} uses '/latest/' - use explicit version instead"
                )
            else:
                url_version = extract_version_from_url(url)
                if url_version and url_version != agent_version:
                    errors.append(
                        f"Binary URL for {platform} has version "
                        f"{url_version}, expected {agent_version}"
                    )

    # Check npm packages
    if "npx" in distribution:
        package = distribution["npx"].get("package", "")
        if "@latest" in package.lower():
            errors.append(f"npx package uses '@latest' - use explicit version instead: {package}")
        else:
            pkg_version = extract_npm_package_version(package)
            if pkg_version and pkg_version != agent_version:
                errors.append(
                    f"npx package version ({pkg_version}) doesn't match "
                    f"agent version ({agent_version})"
                )

    # Check PyPI packages
    if "uvx" in distribution:
        package = distribution["uvx"].get("package", "")
        if "@latest" in package.lower():
            errors.append(f"uvx package uses '@latest' - use explicit version instead: {package}")
        # Extract version from uvx package
        # (formats: package==version, package>=version, package@version)
        version_match = re.search(r"[=@]+([\d.]+)", package)
        if version_match:
            pkg_version = version_match.group(1)
            if pkg_version != agent_version:
                errors.append(
                    f"uvx package version ({pkg_version}) doesn't match "
                    f"agent version ({agent_version})"
                )

    return errors


def validate_distribution_urls(distribution: dict) -> list[str]:
    """Validate that distribution URLs exist."""
    if SKIP_URL_VALIDATION:
        return []

    errors = []

    # Check binary archive URLs
    if "binary" in distribution:
        for platform, target in distribution["binary"].items():
            if "archive" in target:
                url = target["archive"]
                if not url_exists(url):
                    errors.append(f"Binary archive URL not accessible for {platform}: {url}")

    # Check npm package URLs (registry.npmjs.org)
    seen_npm = set()
    for dist_type in ("npx",):
        if dist_type in distribution:
            package = distribution[dist_type].get("package", "")
            pkg_name = extract_npm_package_name(package)
            if pkg_name and pkg_name not in seen_npm:
                seen_npm.add(pkg_name)
                npm_url = f"https://registry.npmjs.org/{pkg_name}"
                if not url_exists(npm_url):
                    errors.append(f"npm package not found: {pkg_name}")

    # Check PyPI package URLs
    if "uvx" in distribution:
        package = distribution["uvx"].get("package", "")
        pkg_name = extract_pypi_package_name(package)
        pypi_url = f"https://pypi.org/pypi/{pkg_name}/json"
        if not url_exists(pypi_url):
            errors.append(f"PyPI package not found: {pkg_name}")

    return errors


def validate_icon_monochrome(root: ET.Element) -> list[str]:
    """Validate that icon uses currentColor and no hardcoded colors.

    Uses xml.etree.ElementTree to walk all elements, checking fill/stroke
    attributes, inline styles, and <style> blocks — more robust than regex.
    """
    errors = []
    has_current_color = False

    for elem in root.iter():
        # Check fill attribute
        fill = elem.get("fill")
        if fill is not None:
            normalized = fill.strip().lower()
            if normalized == "currentcolor":
                has_current_color = True
            elif normalized not in ALLOWED_FILL_STROKE_VALUES:
                errors.append(f'Icon has hardcoded fill="{fill}" (use currentColor or none)')

        # Check stroke attribute
        stroke = elem.get("stroke")
        if stroke is not None:
            normalized = stroke.strip().lower()
            if normalized == "currentcolor":
                has_current_color = True
            elif normalized not in ALLOWED_FILL_STROKE_VALUES:
                errors.append(f'Icon has hardcoded stroke="{stroke}" (use currentColor or none)')

        # Check inline style attribute for fill/stroke
        style = elem.get("style")
        if style:
            for prop in style.split(";"):
                if ":" not in prop:
                    continue
                name, value = prop.split(":", 1)
                name = name.strip().lower()
                value_raw = value.strip()
                value_lower = value_raw.lower()
                if name == "fill":
                    if value_lower == "currentcolor":
                        has_current_color = True
                    elif value_lower not in ALLOWED_FILL_STROKE_VALUES:
                        errors.append(f"Icon has hardcoded style fill: {value_raw}")
                elif name == "stroke":
                    if value_lower == "currentcolor":
                        has_current_color = True
                    elif value_lower not in ALLOWED_FILL_STROKE_VALUES:
                        errors.append(f"Icon has hardcoded style stroke: {value_raw}")

        # Check <style> elements for CSS rules with fill/stroke
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "style" and elem.text:
            for pattern, attr_name in (
                (r"\bfill\s*:\s*([^;}\s]+)", "fill"),
                (r"\bstroke\s*:\s*([^;}\s]+)", "stroke"),
            ):
                for val in re.findall(pattern, elem.text, re.IGNORECASE):
                    val_lower = val.strip().lower()
                    if val_lower == "currentcolor":
                        has_current_color = True
                    elif val_lower not in ALLOWED_FILL_STROKE_VALUES:
                        errors.append(f"Icon has hardcoded CSS {attr_name}: {val.strip()}")

    if not has_current_color:
        errors.append("Icon must use currentColor for fills/strokes to support theming")

    # Deduplicate errors
    return list(dict.fromkeys(errors))


def validate_icon(icon_path: Path) -> list[str]:
    """Validate icon.svg using an XML parser for robust SVG analysis."""
    errors = []

    try:
        content = icon_path.read_text()
    except Exception as e:
        errors.append(f"Cannot read icon: {e}")
        return errors

    # Reject HTML/XML comments (they break MDX/JSX when icons are embedded in docs)
    if "<!--" in content:
        errors.append("Icon contains HTML comments which break MDX embedding; remove them")

    # Parse SVG as XML
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        errors.append(f"Icon is not valid SVG/XML: {e}")
        return errors

    # Verify root element is <svg> (handle optional namespace)
    root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if root_tag != "svg":
        errors.append(f"Icon root element must be <svg>, got <{root_tag}>")
        return errors

    # Extract dimensions from SVG root attributes
    width_str = root.get("width")
    height_str = root.get("height")
    viewbox = root.get("viewBox")

    vb_width = None
    vb_height = None

    if width_str and height_str:
        try:
            vb_width = float(re.sub(r"[a-z%]+$", "", width_str.strip(), flags=re.IGNORECASE))
            vb_height = float(re.sub(r"[a-z%]+$", "", height_str.strip(), flags=re.IGNORECASE))
        except ValueError:
            pass

    if (vb_width is None or vb_height is None) and viewbox:
        parts = viewbox.split()
        if len(parts) == 4:
            try:
                vb_width = float(parts[2])
                vb_height = float(parts[3])
            except ValueError:
                pass

    if vb_width is None or vb_height is None:
        errors.append("Icon missing width/height attributes and viewBox")
        return errors

    # Check size
    if vb_width != vb_height:
        errors.append(f"Icon must be square (got {vb_width}x{vb_height})")

    if vb_width != PREFERRED_ICON_SIZE or vb_height != PREFERRED_ICON_SIZE:
        size = PREFERRED_ICON_SIZE
        errors.append(f"Icon should be {size}x{size} (got {int(vb_width)}x{int(vb_height)})")

    # Validate monochrome (currentColor) usage
    monochrome_errors = validate_icon_monochrome(root)
    errors.extend(monochrome_errors)

    return errors


def get_base_url():
    """Get base URL from environment or use default."""
    return os.environ.get("REGISTRY_BASE_URL", DEFAULT_BASE_URL)


def load_schema(registry_dir: Path) -> dict | None:
    """Load agent.schema.json if available."""
    schema_path = registry_dir / "agent.schema.json"
    if not schema_path.exists():
        return None
    try:
        with open(schema_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: Could not load agent.schema.json: {e}")
        return None


def validate_against_schema(agent: dict, schema: dict) -> list[str]:
    """Validate agent against JSON schema."""
    if not HAS_JSONSCHEMA:
        return []

    errors = []
    try:
        jsonschema.validate(instance=agent, schema=schema)
    except jsonschema.ValidationError as e:
        # Get the path to the error
        path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "root"
        errors.append(f"Schema validation error at '{path}': {e.message}")
    except jsonschema.SchemaError as e:
        errors.append(f"Invalid schema: {e.message}")

    return errors


def validate_agent(agent: dict, agent_dir: str, schema: dict | None = None) -> list[str]:
    """Validate agent.json and return list of errors."""
    errors = []

    # Validate against JSON schema first
    if schema is not None:
        schema_errors = validate_against_schema(agent, schema)
        if schema_errors:
            errors.extend(schema_errors)
            return errors  # Return early if schema validation fails

    # Check required fields
    missing = REQUIRED_FIELDS - set(agent.keys())
    if missing:
        errors.append(f"Missing required fields: {', '.join(sorted(missing))}")

    # Validate id format
    if "id" in agent:
        agent_id = agent["id"]
        if not agent_id:
            errors.append("Field 'id' cannot be empty")
        elif not agent_id[0].isalpha():
            errors.append("Field 'id' must start with a letter")
        elif not all(c.islower() or c.isdigit() or c == "-" for c in agent_id):
            errors.append("Field 'id' must be lowercase with hyphens only")
        elif agent_id != agent_dir:
            errors.append(f"Field 'id' ({agent_id}) must match directory name ({agent_dir})")

    # Validate version format
    if "version" in agent:
        version = agent["version"]
        parts = version.split(".")
        if len(parts) < 3 or not all(p.isdigit() for p in parts[:3]):
            errors.append(f"Field 'version' ({version}) must be semantic version (e.g., 1.0.0)")

    # Validate distribution
    if "distribution" in agent:
        dist = agent["distribution"]
        if not isinstance(dist, dict) or not dist:
            errors.append("Field 'distribution' must be a non-empty object")
        else:
            unknown_types = set(dist.keys()) - VALID_DISTRIBUTION_TYPES
            if unknown_types:
                errors.append(f"Unknown distribution types: {', '.join(sorted(unknown_types))}")

            # Validate binary platforms
            if "binary" in dist:
                binary = dist["binary"]
                if not isinstance(binary, dict) or not binary:
                    errors.append("Field 'distribution.binary' must be a non-empty object")
                else:
                    unknown_platforms = set(binary.keys()) - VALID_PLATFORMS
                    if unknown_platforms:
                        errors.append(f"Unknown platforms: {', '.join(sorted(unknown_platforms))}")

                    # Warn if not all OS families have at least one platform
                    provided_os_families = {p.split("-")[0] for p in binary if p in VALID_PLATFORMS}
                    missing_os_families = REQUIRED_OS_FAMILIES - provided_os_families
                    if missing_os_families:
                        print(
                            f"Warning: {agent_dir} binary distribution is missing builds for: "
                            f"{', '.join(sorted(missing_os_families))}"
                        )

                    for platform, target in binary.items():
                        if platform in VALID_PLATFORMS:
                            if "archive" not in target:
                                errors.append(f"Platform {platform} missing 'archive' field")
                            else:
                                archive_url = target["archive"].lower()
                                for ext in REJECTED_ARCHIVE_EXTENSIONS:
                                    if archive_url.endswith(ext):
                                        supported = ".zip, .tar.gz, .tgz, .tar.bz2, .tbz2"
                                        errors.append(
                                            f"Platform {platform} archive uses "
                                            f"unsupported format '{ext}'. "
                                            f"Supported formats: {supported}, "
                                            f"or raw binaries"
                                        )
                                        break
                            if "cmd" not in target:
                                errors.append(f"Platform {platform} missing 'cmd' field")

            # Validate package distributions
            for dist_type in ("npx", "uvx"):
                if dist_type in dist:
                    pkg_dist = dist[dist_type]
                    if "package" not in pkg_dist:
                        errors.append(f"Distribution '{dist_type}' missing 'package' field")

    return errors


def process_entry(
    entry_dir: Path,
    entry_file: str,
    entry_type: str,
    schema: dict | None,
    base_url: str,
    seen_ids: dict,
) -> tuple[dict | None, list[str]]:
    """Process a single registry entry. Returns (entry, errors)."""
    entry_path = entry_dir / entry_file

    # Parse JSON with error handling
    try:
        with open(entry_path) as f:
            entry = json.load(f)
    except json.JSONDecodeError as e:
        return None, [f"{entry_dir.name}/{entry_file} is invalid JSON: {e}"]

    # Validate entry
    validation_errors = validate_agent(entry, entry_dir.name, schema)
    if validation_errors:
        return None, [f"{entry_dir.name}/{entry_file} validation failed:"] + [
            f"  - {e}" for e in validation_errors
        ]

    # Validate distribution versions match entry version
    if "distribution" in entry:
        version_errors = validate_distribution_versions(entry["version"], entry["distribution"])
        if version_errors:
            return None, [f"{entry_dir.name} version validation failed:"] + [
                f"  - {e}" for e in version_errors
            ]

    # Check for duplicate IDs
    entry_id = entry["id"]
    if entry_id in seen_ids:
        return None, [
            f"Duplicate ID '{entry_id}' in {entry_dir.name}/ (already in {seen_ids[entry_id]}/)"
        ]
    seen_ids[entry_id] = entry_dir.name

    # Validate distribution URLs
    if "distribution" in entry:
        url_errors = validate_distribution_urls(entry["distribution"])
        if url_errors:
            return None, [f"{entry_dir.name} distribution URL validation failed:"] + [
                f"  - {e}" for e in url_errors
            ]

    # Validate icon (required)
    icon_path = entry_dir / "icon.svg"
    if not icon_path.exists():
        return None, [f"{entry_dir.name}/icon.svg is missing (icon is required)"]
    icon_errors = validate_icon(icon_path)
    if icon_errors:
        return None, [f"{entry_dir.name}/icon.svg validation failed:"] + [
            f"  - {e}" for e in icon_errors
        ]
    entry["icon"] = f"{base_url}/{entry_id}.svg"

    return entry, []


def build_registry(dry_run: bool = False):
    """Build registry.json from agent directories.

    Args:
        dry_run: If True, validate and report what would be built without writing to dist/.
    """
    registry_dir = Path(__file__).parent.parent.parent
    base_url = get_base_url()
    agents = []
    seen_ids = {}
    has_errors = False

    # Load schema for validation
    schema = load_schema(registry_dir)
    if schema and not HAS_JSONSCHEMA:
        print("Warning: jsonschema not installed, skipping schema validation")
        print("  Install with: pip install jsonschema")

    for entry_dir in sorted(registry_dir.iterdir()):
        if not entry_dir.is_dir() or should_skip_dir(entry_dir.name):
            continue

        agent_json_path = entry_dir / "agent.json"

        if not agent_json_path.exists():
            print(f"Warning: {entry_dir.name}/ has no agent.json, skipping")
            continue

        entry, errors = process_entry(entry_dir, "agent.json", "agent", schema, base_url, seen_ids)
        if errors:
            for error in errors:
                print(f"Error: {error}")
            has_errors = True
            continue
        agents.append(entry)
        print(f"Added agent: {entry['id']} v{entry['version']}")

    if has_errors:
        print("\nBuild failed due to validation errors")
        sys.exit(1)

    if not agents:
        print("\nWarning: No agents found")

    # Agents excluded from registry.json (default registry)
    DEFAULT_EXCLUDE_IDS = {"github-copilot"}
    default_agents = [a for a in agents if a["id"] not in DEFAULT_EXCLUDE_IDS]

    # Agents excluded from registry-for-jetbrains.json
    JETBRAINS_EXCLUDE_IDS = {"codex-acp", "github-copilot-cli"}

    # Agents flagged as bundled in the JetBrains registry
    JETBRAINS_BUNDLED_IDS = {"claude-acp", "junie", "codex-acp", "gemini"}

    def patch_agent_for_jetbrains(agent):
        patched = copy.deepcopy(agent)
        if patched["id"] == "claude-acp":
            assert "npx" in patched["distribution"], "claude-acp must have npx distribution"
            patched["distribution"]["npx"].setdefault("args", []).append("--hide-claude-auth")
        if patched["id"] in JETBRAINS_BUNDLED_IDS:
            patched["bundled"] = True
        return patched

    jetbrains_agents = [
        patch_agent_for_jetbrains(a) for a in agents if a["id"] not in JETBRAINS_EXCLUDE_IDS
    ]

    if dry_run:
        print(f"\nDry run: validated {len(agents)} agents successfully")
        print(
            f"  registry.json would contain {len(default_agents)} agents"
            f" (excluded: {', '.join(sorted(DEFAULT_EXCLUDE_IDS))})"
        )
        print(
            f"  registry-for-jetbrains.json would contain "
            f"{len(jetbrains_agents)} agents (excluded: {', '.join(sorted(JETBRAINS_EXCLUDE_IDS))})"
        )
        return

    # Create dist directory
    dist_dir = registry_dir / "dist"
    dist_dir.mkdir(exist_ok=True)

    # Write registry.json
    registry = {"version": REGISTRY_VERSION, "agents": default_agents, "extensions": []}
    output_path = dist_dir / "registry.json"
    with open(output_path, "w") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")

    # Write registry-for-jetbrains.json
    jetbrains_registry = {
        "version": REGISTRY_VERSION,
        "agents": jetbrains_agents,
    }
    jetbrains_output_path = dist_dir / "registry-for-jetbrains.json"
    with open(jetbrains_output_path, "w") as f:
        json.dump(jetbrains_registry, f, indent=2)
        f.write("\n")

    # Copy icons to dist
    for entry in agents:
        entry_id = entry["id"]
        icon_src = registry_dir / entry_id / "icon.svg"
        if icon_src.exists():
            icon_dst = dist_dir / f"{entry_id}.svg"
            icon_dst.write_bytes(icon_src.read_bytes())

    # Copy schema files to dist
    for schema_file in ("agent.schema.json", "registry.schema.json"):
        schema_src = registry_dir / schema_file
        if schema_src.exists():
            schema_dst = dist_dir / schema_file
            schema_dst.write_bytes(schema_src.read_bytes())

    print(f"\nBuilt dist/ with {len(agents)} total agents")
    print(
        f"  registry.json: {len(default_agents)} agents"
        f" (excluded: {', '.join(sorted(DEFAULT_EXCLUDE_IDS))})"
    )
    print(
        f"  registry-for-jetbrains.json: {len(jetbrains_agents)} agents"
        f" (excluded: {', '.join(sorted(JETBRAINS_EXCLUDE_IDS))})"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build aggregated registry.json")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate all agents without writing to dist/",
    )
    args = parser.parse_args()
    build_registry(dry_run=args.dry_run)
