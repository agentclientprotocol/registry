# ACP Registry

https://agentclientprotocol.com/registry

Registry of agents implementing the [Agent Client Protocol, ACP](https://github.com/agentclientprotocol/agent-client-protocol).

> **Authentication Required**: This registry maintains a curated list of **agents that support user authentication**.
>
> Users must be able to authenticate themselves with agents to use them.
> All agents are verified via CI to ensure they return valid `authMethods` in the ACP handshake.
> See [AUTHENTICATION.md](AUTHENTICATION.md) for implementation details and the [ACP auth methods proposal](https://github.com/agentclientprotocol/agent-client-protocol/blob/main/docs/rfds/auth-methods.mdx) for the specification.


## Usage

Fetch the registry index:

```
https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json
```

## Registry Format

See [FORMAT.md](FORMAT.md) for the registry schema, distribution types, and platform targets.

## Automatic Version Updates

Agent versions are automatically updated via a cron job that runs hourly. It checks for new releases across all supported distribution types (npm, PyPI, GitHub releases) and commits updates directly to `main`.

## Adding an Agent

See [CONTRIBUTING.md](CONTRIBUTING.md) for instructions.

## Local Validation

Run the registry tooling in Docker to keep downloads, caches, and auth-related state isolated from your host machine:

```bash
# Validate schema/build output in a container
scripts/run-registry-docker.sh uv run --with jsonschema .github/workflows/build_registry.py

# Verify registered agents in a container
scripts/run-registry-docker.sh python3 .github/workflows/verify_agents.py --auth-check

# Generate the protocol feature matrix in a container
scripts/run-protocol-matrix.sh

# Generate a capabilities-only matrix table in a container
scripts/run-protocol-matrix.sh --table-mode capabilities

# Reuse unchanged agent versions from the previous snapshot
scripts/run-protocol-matrix.sh --table-mode capabilities --changed-only
```

The container keeps state under `.docker-state/` in the repo and disables Python keyring backends to avoid host keychain prompts during local verification.
Set `ACP_PROTOCOL_MATRIX_SKIP_AGENTS=crow-cli` to skip specific agents during matrix generation.

## License

This registry is licensed under the [Apache License 2.0](LICENSE). Individual agents are subject to their own licenses.
