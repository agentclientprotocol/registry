# ACP Agent Registry

> ⚠️ **Work in Progress**: This registry is under active development. Format and contents may change.

A registry of agents implementing the [Agent Client Protocol (ACP)](https://github.com/agentclientprotocol/agent-client-protocol).

> **Note**: This registry only includes agents that support authentication. Agents must implement auth flows to be listed here.

## Included Agents

| Agent                                                             | Description                                                        |
|-------------------------------------------------------------------|:-------------------------------------------------------------------|
| [Auggie CLI](https://github.com/augmentcode/auggie-zed-extension) | Augment Code's software agent with industry-leading context engine |
| [Codex CLI](https://github.com/zed-industries/codex-acp)          | OpenAI's coding assistant                                          |
| [Gemini CLI](https://github.com/google-gemini/gemini-cli)         | Google's official CLI for Gemini                                   |
| [Mistral Vibe](https://github.com/mistralai/mistral-vibe)         | Mistral's open-source coding assistant                             |
| [OpenCode](https://github.com/sst/opencode)                       | The open source coding agent                                       |
| [Qwen Code](https://github.com/QwenLM/qwen-code)                  | Alibaba's Qwen coding assistant                                    |

## Usage

Fetch the registry index:

```
https://github.com/agentclientprotocol/registry/releases/latest/download/registry.json
```

## Registry Format

```json
{
  "version": "1.0.0",
  "agents": [
    {
      "id": "agent-id",
      "name": "Agent Name",
      "version": "1.0.0",
      "description": "Agent description",
      "repository": "https://github.com/...",
      "authors": ["Author Name"],
      "license": "MIT",
      "icon": "https://.../agent-id.svg",
      "distribution": {
        "binary": {
          "darwin-aarch64": {
            "archive": "https://...",
            "cmd": "./agent",
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
  ]
}
```

## Distribution Types

| Type     | Description                   | Command                |
|----------|-------------------------------|------------------------|
| `binary` | Platform-specific executables | Download, extract, run |
| `npx`    | npm packages                  | `npx <package> [args]` |
| `uvx`    | PyPI packages via uv          | `uvx <package> [args]` |

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

## Adding an Agent

See [CONTRIBUTING.md](CONTRIBUTING.md) for instructions on submitting a new agent.

## License

This registry is open source. Individual agents are subject to their own licenses.
