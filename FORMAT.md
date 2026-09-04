# Registry Format

The registry contains agents:

```json
{
  "version": "1.0.0",
  "agents": [...]
}
```

Each agent has the following structure:

```json
{
  "id": "entry-id",
  "name": "Entry Name",
  "version": "1.0.0",
  "description": "Entry description",
  "repository": "https://github.com/...",
  "website": "https://example.com/docs",
  "authors": ["Author Name"],
  "license": "MIT",
  "icon": "https://.../entry-id.svg",
  "distribution": {
    "binary": {
      "darwin-aarch64": {
        "archive": "https://...",
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "cmd": "./executable",
        "args": ["serve"],
        "env": {}
      }
    },
    "npx": {
      "package": "@scope/package",
      "args": ["--acp"]
    },
    "uvx": {
      "package": "package-name",
      "args": ["serve"]
    }
  }
}
```

## Preview Channel

An agent may declare an optional `preview` block holding **exactly two** fields — `version` and `distribution`. It describes the same agent on an unstable release channel; all other metadata (`name`, `description`, `repository`, `authors`, `license`, icon) is shared with the stable entry and must never be duplicated.

```json
{
  "id": "codex-acp",
  "version": "1.8.0",
  "distribution": {
    "npx": { "package": "@agentclientprotocol/codex-acp@1.8.0" }
  },
  "preview": {
    "version": "1.9.0-preview.1",
    "distribution": {
      "npx": { "package": "@agentclientprotocol/codex-acp@1.9.0-preview.1" }
    }
  }
}
```

`preview.distribution` is a full distribution object validated against the same schema definitions as the root `distribution`, restricted to `npx` and `uvx`. **`binary` preview distributions are not supported.**

### Version scheme

Preview versions use `X.Y.Z-preview.N`, where `X.Y.Z` is the next, not-yet-released stable version and `N` is a 1-based counter:

```
1.9.0-preview.1  →  1.9.0-preview.2  →  …  →  1.9.0-preview.10  →  1.9.0 (stable)
```

This is valid semver, so precedence works out as expected: `1.9.0-preview.N` ranks below the `1.9.0` release it targets, and `preview.10` ranks above `preview.2` because a purely numeric prerelease identifier is compared numerically. Shapes like `1.0-preview-1`, `1.9.0-rc.1` or `1.9.0+preview.1` are rejected.

The root `version` field is always a plain `X.Y.Z` release — a prerelease there is a validation error.

### Highest of both channels wins

`preview.version` means *"the newest version we know about"*, not *"a prerelease"*, so it may legitimately hold a plain `X.Y.Z` release. When the stable channel overtakes the preview line (stable ships `1.9.1` while the newest preview is still `1.9.0-preview.1`), that is **not** an error:

| Manifest state                                          | Preview registry serves           |
| ------------------------------------------------------- | --------------------------------- |
| `version: 1.8.0`, `preview.version: 1.9.0-preview.2`    | `1.9.0-preview.2`                 |
| `version: 1.9.1`, `preview.version: 1.9.0-preview.1`    | `1.9.1` (stable is newer)         |
| `version: 1.9.1`, `preview.version: 1.9.1`              | `1.9.1` (identical to stable)     |
| no `preview` block                                      | the stable entry                  |

A stale preview block therefore self-heals on the next hourly run instead of failing the build.

### Published preview entries

The `preview` key never appears in any published registry. It is stripped from `registry.json` and `registry-for-jetbrains.json`, and in `registry-for-jetbrains-preview.json` the previewed agent appears as an **ordinary agent entry** with `version` and `distribution` substituted wholesale by the preview values:

```json
{
  "id": "codex-acp",
  "name": "Codex",
  "version": "1.9.0-preview.1",
  "description": "ACP adapter for OpenAI's coding assistant",
  "repository": "https://github.com/agentclientprotocol/codex-acp",
  "distribution": {
    "npx": { "package": "@agentclientprotocol/codex-acp@1.9.0-preview.1" }
  }
}
```

`registry-for-jetbrains-preview.json` is a complete, drop-in replacement for `registry-for-jetbrains.json`: agents without a `preview` block appear at their stable version, so a client points at one URL and never merges two files.

### The preview channel is unverified

Preview is an explicitly unstable, best-effort channel. Preview distributions are **never** launched or auth-checked, their URLs are **not** probed for reachability, and they do **not** appear in the nightly protocol matrix. The only checks applied are offline ones: schema validation, and the requirement that the package spec's pinned version equals `preview.version`.

## Distribution Types

| Type     | Description                   | Command                |
| -------- | ----------------------------- | ---------------------- |
| `binary` | Platform-specific executables | Download, extract, run |
| `npx`    | npm packages                  | `npx <package> [args]` |
| `uvx`    | PyPI packages via uv          | `uvx <package> [args]` |

**Supported archive formats for binary distribution:** `.zip`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, or raw binaries. Installer formats (`.dmg`, `.pkg`, `.deb`, `.rpm`, `.msi`, `.appimage`) are not supported.

**Archive integrity check:** Each binary distribution may include a `sha256` with the SHA-256 digest of the archive (64 lowercase or uppercase hex characters).

## Icons

Icons should be SVG format with a **preferred size of 16x16**.

> **Warning**: Icons larger than 16x16 may be scaled down and lose quality. Icons with non-square aspect ratios may display incorrectly in some clients.

## Platform Targets

For binary distribution, use these platform identifiers:

- `darwin-aarch64` - macOS Apple Silicon
- `darwin-x86_64` - macOS Intel
- `linux-aarch64` - Linux ARM64
- `linux-x86_64` - Linux x86_64
- `windows-aarch64` - Windows ARM64
- `windows-x86_64` - Windows x86_64
