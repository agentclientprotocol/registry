# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build Commands

```bash
# Build registry (validates all agents and outputs to dist/)
uv run --with jsonschema .github/workflows/build_registry.py

# Build without schema validation (if jsonschema not available)
python .github/workflows/build_registry.py
```

## Architecture

This is a registry of ACP (Agent Client Protocol) agents. The structure is:

```
<id>/
├── agent.json      # Agent metadata and distribution info
└── icon.svg        # Icon: 16x16 SVG, monochrome with currentColor (required)
```

**Build process** (`.github/workflows/build_registry.py`):

1. Scans directories for `agent.json` files
2. Validates against `agent.schema.json` (JSON Schema)
3. Validates icons (16x16 SVG, monochrome with `currentColor`)
4. Aggregates into `dist/registry.json`
5. Copies icons to `dist/<id>.svg`

**CI/CD** (`.github/workflows/build-registry.yml`):

- PRs: Runs validation only
- Push to main: Validates, then publishes versioned + `latest` GitHub releases

## Validation Rules

- `id`: lowercase, hyphens only, must match directory name
- `version`: semantic versioning (e.g., `1.0.0`)
- `distribution`: at least one of `binary`, `npx`, `uvx`
- `binary` distribution: builds for all operating systems (darwin, linux, windows) are recommended; missing OS families produce a warning
- `binary` archives must use supported formats (`.zip`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, or raw binaries); installer formats (`.dmg`, `.pkg`, `.deb`, `.rpm`, `.msi`, `.appimage`) are rejected
- `icon.svg`: must be SVG format, 16x16, monochrome using `currentColor` (enables theming)
- **URL validation**: All distribution URLs must be accessible (binary archives, npm/PyPI packages)

Set `SKIP_URL_VALIDATION=1` to bypass URL checks during local development.

## Updating Agent Versions

### Automated Updates

Agent versions are automatically updated via `.github/workflows/update-versions.yml`:

- **Schedule:** Runs hourly (cron: `0 * * * *`)
- **Scope:** Checks all agents in root and `_not_yet_unsupported/`
- **Supported distributions:** `npx` (npm), `uvx` (PyPI), `binary` (GitHub releases)

```bash
# Dry run - check for available updates
uv run .github/workflows/update_versions.py

# Apply updates locally
uv run .github/workflows/update_versions.py --apply

# Check specific agents only
uv run .github/workflows/update_versions.py --agents gemini,github-copilot
```

The workflow can also be triggered manually via GitHub Actions with options to apply updates and filter by agent IDs.

### Manual Updates

To update agents manually:

1. **For npm packages** (`npx` distribution): Check latest version at `https://registry.npmjs.org/<package>/latest`
2. **For GitHub binaries** (`binary` distribution): Check latest release at `https://api.github.com/repos/<owner>/<repo>/releases/latest`

Update `agent.json`:

- Update the `version` field
- Update version in all distribution URLs (use replace-all for consistency)
- For npm: update `package` field (e.g., `@google/gemini-cli@0.22.5`)
- For binaries: update archive URLs with new version/tag

Run build to validate: `uv run --with jsonschema .github/workflows/build_registry.py`

**Note:** Agents in `_not_yet_unsupported/` should remain there - do not move them to the main registry. They can still have their versions updated in place.

## Distribution Types

- `binary`: Platform-specific archives (`darwin-aarch64`, `linux-x86_64`, etc.). Supported archive formats: `.zip`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, or raw binaries. Supporting all operating systems (darwin, linux, windows) is recommended.
- `npx`: npm packages (cross-platform by default)
- `uvx`: PyPI packages (cross-platform by default)

## Icon Requirements

Icons must be:

- **SVG format** (only `.svg` files accepted)
- **16x16 dimensions** (via width/height attributes or viewBox)
- **Monochrome using `currentColor`** - all fills and strokes must use `currentColor` or `none`

Using `currentColor` enables icons to adapt to different themes (light/dark mode) automatically.

**Valid example:**

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path fill="currentColor" d="M..."/>
</svg>
```

**Invalid patterns:**

- Hardcoded colors: `fill="#FF5500"`, `fill="red"`, `stroke="rgb(0,0,0)"`
- Missing currentColor: `fill` or `stroke` without `currentColor`

## Authentication Validation

Agents must support ACP authentication. The CI verifies auth via `.github/workflows/verify_agents.py --auth-check`.

**Requirements:**

- Return `authMethods` array in `initialize` response
- At least one method must have type `"agent"` or `"terminal"`

See [AUTHENTICATION.md](AUTHENTICATION.md) for details on implementing auth methods.
