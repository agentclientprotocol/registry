# Authentication Requirements

This document describes the authentication requirements for agents to be included in the ACP Registry.

## Overview

To be listed in this registry, an agent **must support at least one of the following authentication methods**: **Agent Auth** or **Terminal Auth**. While the [ACP specification](https://agentclientprotocol.com/rfds/auth-methods) defines additional authentication methods (such as Environment Variable Auth), only Agent Auth and Terminal Auth are currently supported by this registry.

This requirement ensures that clients can provide a consistent authentication experience for users.

## Supported Authentication Methods

- **Agent Auth** - Agent handles OAuth authentication flow
- **Terminal Auth** - Interactive terminal-based authentication

## Agent Auth

Agent Auth is the default authentication method where the agent manages the entire OAuth flow independently.

### How It Works

1. When authentication is required, the client triggers the agent's auth flow
2. The agent starts a **local HTTP server** on the user's machine to receive the OAuth callback
3. The agent **opens the user's default browser** with the OAuth authorization URL
4. The user authenticates with the provider (e.g., Google, GitHub, OpenAI) in the browser
5. After successful authentication, the provider redirects back to the agent's local HTTP server with an authorization code
6. The agent exchanges the authorization code for access tokens
7. The agent stores the credentials securely and completes the authentication

### Implementation

Agents should declare Agent Auth support in their `AUTH_REQUIRED` error response:

```json
{
  "id": "123",
  "name": "Agent",
  "description": "Authenticate through agent",
  "type": "agent"
}
```

When `type` is not specified, `"agent"` is assumed as the default for backward compatibility.

## Terminal Auth

Terminal Auth enables agents to run an interactive setup experience within a terminal environment. This is useful for agents that require a Text User Interface (TUI) for authentication.

### How It Works

1. The client launches the agent binary with additional setup arguments
2. The agent presents an interactive terminal interface
3. The user completes the authentication flow within the terminal
4. Once authenticated, the agent is ready for standard ACP communication

### Implementation

Agents should declare Terminal Auth support with additional arguments and environment variables:

```json
{
  "id": "123",
  "name": "Run in terminal",
  "description": "Interactive terminal setup",
  "type": "terminal",
  "args": ["--setup"],
  "env": {
    "VAR1": "value1"
  }
}
```

**Key points:**

- The `args` array specifies additional command-line arguments (e.g., `--setup`, `--login`)
- The `env` object defines environment variables to pass to the process
- These **replace** the default args/env for the agent during the setup flow
- The agent should handle its interactive login flow separately from standard ACP operation

### Example Usage

If an agent normally runs as:
```bash
my-agent serve --acp
```

With Terminal Auth configured as `args: ["--setup"]`, the client would invoke:
```bash
my-agent --setup
```

The agent then presents its interactive authentication UI. Once setup is complete, the client can run the agent with its normal arguments.

## References

- [ACP Authentication Methods RFD](https://agentclientprotocol.com/rfds/auth-methods)
- [Agent Client Protocol GitHub](https://github.com/agentclientprotocol/agent-client-protocol)
- [OAuth 2.0 Specification](https://oauth.net/2/)
