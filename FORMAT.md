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
  "authors": ["Author Name"],
  "license": "MIT",
  "icon": "https://.../entry-id.svg",
  "distribution": {
    "binary": {
      "darwin-aarch64": {
        "archive": "https://...",
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

## Distribution Types

| Type     | Description                   | Command                |
| -------- | ----------------------------- | ---------------------- |
| `binary` | Platform-specific executables | Download, extract, run |
| `npx`    | npm packages                  | `npx <package> [args]` |
| `uvx`    | PyPI packages via uv          | `uvx <package> [args]` |

**Supported archive formats for binary distribution:** `.zip`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, or raw binaries. Installer formats (`.dmg`, `.pkg`, `.deb`, `.rpm`, `.msi`, `.appimage`) are not supported.

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
