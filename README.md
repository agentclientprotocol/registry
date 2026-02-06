# ACP Registry

> ⚠️ **Work in Progress**: This registry is under active development. Format and contents may change.

A registry of agents implementing the [Agent Client Protocol, ACP](https://github.com/agentclientprotocol/agent-client-protocol).

> **Authentication Required**: This registry maintains a curated list of **agents that support user authentication**.
>
> Users must be able to authenticate themselves with agents to use them.
> All agents are verified via CI to ensure they return valid `authMethods` in the ACP handshake.
> See [AUTHENTICATION.md](AUTHENTICATION.md) for implementation details and the [ACP auth methods proposal](https://github.com/agentclientprotocol/agent-client-protocol/blob/main/docs/rfds/auth-methods.mdx) for the specification.

## Included Agents

| Agent                                                                       | Description                                                                       |
|-----------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| [Auggie CLI](https://github.com/augmentcode/auggie-zed-extension)           | Augment Code's powerful software agent, backed by industry-leading context engine |
| [Claude Code](https://github.com/zed-industries/claude-code-acp)            | ACP adapter for Claude Code                                                       |
| [Codex CLI](https://github.com/zed-industries/codex-acp)                    | ACP adapter for OpenAI's coding assistant                                         |
| Factory Droid                                                               | Factory Droid - AI coding agent powered by Factory AI                             |
| [Gemini CLI](https://github.com/google-gemini/gemini-cli)                   | Google's official CLI for Gemini                                                  |
| [GitHub Copilot](https://github.com/github/copilot-language-server-release) | GitHub's AI pair programmer                                                       |
| [Mistral Vibe](https://github.com/mistralai/mistral-vibe)                   | Mistral's open-source coding assistant                                            |
| [OpenCode](https://github.com/sst/opencode)                                 | The open source coding agent                                                      |
| [Qwen Code](https://github.com/QwenLM/qwen-code)                            | Alibaba's Qwen coding assistant                                                   |

## Usage

Fetch the registry index:

```
https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json
```

## Registry Format

See [FORMAT.md](FORMAT.md) for the registry schema, distribution types, and platform targets.

## Adding an Agent

See [CONTRIBUTING.md](CONTRIBUTING.md) for instructions.

## License

This registry is licensed under the [Apache License 2.0](LICENSE). Individual agents are subject to their own licenses.
