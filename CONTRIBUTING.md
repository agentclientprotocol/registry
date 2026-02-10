# Contributing to the ACP Registry

## Adding a New Agent or Extension

1. **Fork this repository**

2. **Create a directory for your entry**

   ```
   mkdir <id>/
   ```

   The directory name must match your entry's `id` field.

3. **Create `agent.json` or `extension.json`**

   Use `agent.json` for agents, `extension.json` for extensions. Both use the same schema.

   ```json
   {
     "id": "your-agent-id",
     "name": "Your Agent Name",
     "version": "1.0.0",
     "description": "Brief description of your agent",
     "repository": "https://github.com/your-org/your-repo",
     "authors": ["Your Name <email@example.com>"],
     "license": "MIT",
     "distribution": {
       // At least one distribution method required
     }
   }
   ```

4. **Add an icon** (optional but recommended)

   Place an SVG icon at `<agent-id>/icon.svg`.

   **Icon requirements:**
   - **16x16 SVG** - larger icons may be scaled down and lose quality
   - **Monochrome using `currentColor`** - enables theme support (light/dark mode)

   Example:
   ```svg
   <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
     <path fill="currentColor" d="M..."/>
   </svg>
   ```

   > **Warning**: Icons with hardcoded colors (`fill="#FF0000"`, `fill="red"`, etc.) will fail validation. Use `fill="currentColor"` or `fill="none"` only.

5. **Submit a Pull Request**

   The CI will validate your `agent.json` against the schema.

## Distribution Options

### Binary Distribution

For standalone executables. At least one platform is required; providing builds for all operating systems (macOS, Linux, and Windows) is recommended but not mandatory.

> **Supported archive formats:** `.zip`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, or raw binaries. Installer formats (`.dmg`, `.pkg`, `.deb`, `.rpm`, `.msi`, `.appimage`) are not supported.

```json
{
  "distribution": {
    "binary": {
      "darwin-aarch64": {
        "archive": "https://github.com/.../darwin-arm64.tar.gz",
        "cmd": "./your-binary",
        "args": ["acp"]
      },
      "darwin-x86_64": {
        "archive": "https://github.com/.../darwin-x64.tar.gz",
        "cmd": "./your-binary",
        "args": ["acp"]
      },
      "linux-aarch64": {
        "archive": "https://github.com/.../linux-arm64.tar.gz",
        "cmd": "./your-binary",
        "args": ["acp"]
      },
      "linux-x86_64": {
        "archive": "https://github.com/.../linux-x64.tar.gz",
        "cmd": "./your-binary",
        "args": ["acp"]
      },
      "windows-x86_64": {
        "archive": "https://github.com/.../windows-x64.zip",
        "cmd": "your-binary.exe",
        "args": ["acp"]
      }
    }
  }
}
```

Supported platforms: `darwin-aarch64`, `darwin-x86_64`, `linux-aarch64`, `linux-x86_64`, `windows-aarch64`, `windows-x86_64`

> **Note**: Providing builds for all operating systems is recommended. Missing OS families will produce a warning during validation but will not block the build.

### npm Package (npx)

```json
{
  "distribution": {
    "npx": {
      "package": "@your-scope/your-package@1.0.0",
      "args": ["--acp"]
    }
  }
}
```

### PyPI Package (uvx)

```json
{
  "distribution": {
    "uvx": {
      "package": "your-package",
      "args": ["serve", "--acp"]
    }
  }
}
```

## Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier (lowercase, hyphens allowed) |
| `name` | string | Display name |
| `version` | string | Semantic version |
| `description` | string | Brief description |
| `distribution` | object | At least one distribution method |

## Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `repository` | string | Source code URL |
| `authors` | array | List of author names/emails |
| `license` | string | SPDX license identifier |

## Automatic Version Updates

Once your agent is in the registry, **versions are updated automatically every hour**. The registry checks for new releases on:

- **npm** - latest published version
- **PyPI** - latest published version
- **GitHub Releases** - latest release tag and assets

You don't need to submit a PR for version bumps.

## Manual Updates

To manually update your agent or extension (e.g., changing description, adding platforms):

1. Fork and update the `agent.json` or `extension.json` file
2. Submit a Pull Request
3. CI will validate and merge will trigger a new registry release

## Validation

All submissions are automatically validated by CI. Here's what gets checked:

### Schema Validation

Entries are validated against the [JSON Schema](agent.schema.json).

### ID Validation

- Must be lowercase letters, digits, and hyphens only
- Must start with a letter
- Must match the directory name
- Must be unique across all agents and extensions

### Version Validation

- Must be semantic version format (`x.y.z`, e.g., `1.0.0`)
- All version parts must be numeric

### Distribution Validation

**Structure:**
- At least one distribution method required (`binary`, `npx`, or `uvx`)
- Binary distributions require `archive` and `cmd` fields per platform
- Package distributions (`npx`, `uvx`) require `package` field

**Platforms** (for binary):
- `darwin-aarch64`, `darwin-x86_64`
- `linux-aarch64`, `linux-x86_64`
- `windows-aarch64`, `windows-x86_64`

**Archive formats** (for binary):
- Supported: `.zip`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, or raw binaries
- Rejected: `.dmg`, `.pkg`, `.deb`, `.rpm`, `.msi`, `.appimage` (installer formats are not supported)

**Cross-platform coverage** (for binary):
- Providing builds for all operating systems (darwin, linux, windows) is recommended
- Missing OS families will produce a warning but will not fail validation

**Version matching:**
- Distribution versions must match the entry's `version` field
- Binary URLs containing version (e.g., `/download/v1.0.0/`) are checked
- npm package versions (`@scope/pkg@1.0.0`) are checked
- PyPI package versions (`pkg==1.0.0` or `pkg@1.0.0`) are checked

**No `latest` allowed:**
- Binary URLs must not contain `/latest/`
- npm packages must not use `@latest`
- PyPI packages must not use `@latest`

### URL Accessibility

All distribution URLs must be accessible:

- Binary archive URLs must return HTTP 200
- npm packages must exist on registry.npmjs.org
- PyPI packages must exist on pypi.org

### Icon Validation

If an `icon.svg` is provided:

- Must be exactly **16x16** pixels (via `width`/`height` attributes or `viewBox`)
- Must be **square** (width equals height)
- Must be **monochrome** using `currentColor`:
  - `fill` attributes: only `currentColor`, `none`, or `inherit` allowed
  - `stroke` attributes: only `currentColor`, `none`, or `inherit` allowed
  - No hardcoded colors (`#FF0000`, `red`, `rgb(...)`, etc.)

### Authentication Validation

Agents are verified to support ACP authentication methods as described in [AUTHENTICATION.md](AUTHENTICATION.md). The CI runs:

```bash
python3 .github/workflows/verify_agents.py --auth-check
```

**What gets checked:**
- Agent must return `authMethods` in the `initialize` response
- At least one method must have `type: "agent"` or `type: "terminal"`
- See [AUTHENTICATION.md](AUTHENTICATION.md) for implementation details

**Verify your agent locally:**

```bash
# Verify a single agent
python3 .github/workflows/verify_agents.py --auth-check --agent your-agent-id

# Verify multiple agents
python3 .github/workflows/verify_agents.py --auth-check --agent agent1,agent2
```

### Run Validation Locally

```bash
uv run --with jsonschema .github/workflows/build_registry.py
```

To skip URL accessibility checks (useful for testing before publishing):

```bash
SKIP_URL_VALIDATION=1 uv run --with jsonschema .github/workflows/build_registry.py
```
