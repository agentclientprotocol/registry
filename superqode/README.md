# SuperQode

SuperQode is a harness engineering coding agent, optimized for local and open
models. Unlike agents with a fixed loop, the loop SuperQode runs is a
**HarnessSpec**: a portable YAML contract in your repository that controls
model routing, tools, memory, sandbox, approvals, and checks — and that you
can version, measure with eval scorecards, and optimize.

## How sessions resolve their harness

Each ACP session picks its HarnessSpec from the project you have open:

1. `superqode.local.yaml` in the session directory
2. `harness.yaml` in the session directory
3. Specs under `.superqode/harness/` (and other conventional harness dirs)
4. The built-in coding template as a fallback

## Model configuration

The provider and model come from the spec's `model_policy.primary`
(for example `ollama/qwen3-coder`), or from the environment:

```bash
SUPERQODE_ACP_PROVIDER=ollama
SUPERQODE_ACP_MODEL=qwen3-coder
```

Run the "Set up SuperQode" authentication step to detect your hardware,
pick a local model, and generate a starter harness for the project
(`superqode local init --repo .`). Hosted/BYOK providers work through the
same spec with your usual provider API keys.

## Links

- [Documentation](https://superagenticai.github.io/superqode/)
- [Harness engineering guide](https://superagenticai.github.io/superqode/harness-engineering/)
- [Source](https://github.com/SuperagenticAI/superqode)
