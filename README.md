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

## Adding an Agent

See [CONTRIBUTING.md](CONTRIBUTING.md) for instructions.

## License

This registry is licensed under the [Apache License 2.0](LICENSE). Individual agents are subject to their own licenses.
