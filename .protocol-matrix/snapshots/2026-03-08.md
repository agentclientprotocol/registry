# ACP Protocol Adaptation Matrix — 2026-03-08

_Generated at 2026-03-08T05:38:37+00:00_

- Agents in report: **26**
- Probed this run: **26**
- Reused unchanged versions: **0**
- `initialize` success: **26**
- `session/new` returned `auth_required`: **19**

Legend: `Capabilities` lists the capabilities advertised in the `initialize` response via `agentCapabilities` and `sessionCapabilities`.

```text
Agent               Version    Dist    Init  Auth             Capabilities                                           
------------------  ---------  ------  ----  ---------------  -------------------------------------------------------
amp-acp             0.7.0      binary  ok    terminal         -                                                      
auggie              0.18.1     npx     ok    terminal         loadSession, session/list                              
autohand            0.2.1      npx     ok    terminal         loadSession, session/list, session/fork, session/resume
claude-acp          0.20.2     npx     ok    terminal         loadSession, session/list, session/fork, session/resume
cline               2.6.1      npx     ok    agent            loadSession                                            
codebuddy-code      2.56.0     npx     ok    agent            loadSession                                            
codex-acp           0.9.5      npx     ok    agent            loadSession, session/list                              
corust-agent        0.3.7      binary  ok    agent            -                                                      
cursor              0.1.0      binary  ok    agent            loadSession                                            
dimcode             0.0.15     npx     ok    agent            loadSession, session/list, session/resume              
factory-droid       0.70.0     npx     ok    agent            loadSession, session/list, session/resume              
gemini              0.32.1     npx     ok    agent            loadSession                                            
github-copilot      1.448.0    npx     ok    agent            loadSession                                            
github-copilot-cli  1.0.2      npx     ok    terminal         loadSession, session/list                              
goose               1.27.2     binary  ok    agent            loadSession, session/list                              
junie               888.173.0  npx     ok    agent, terminal  loadSession, session/list, session/resume              
kilo                7.0.40     npx     ok    terminal         loadSession, session/list, session/fork, session/resume
kimi                1.17.0     binary  ok    terminal         loadSession, session/list, session/resume              
minion-code         0.1.39     uvx     ok    agent            -                                                      
mistral-vibe        2.3.0      binary  ok    terminal         loadSession, session/list                              
nova                1.0.69     npx     ok    terminal         loadSession, session/list, session/fork, session/resume
opencode            1.2.21     binary  ok    terminal         loadSession, session/list, session/fork, session/resume
pi-acp              0.0.22     npx     ok    terminal         loadSession, session/list                              
qoder               0.1.29     npx     ok    terminal         loadSession                                            
qwen-code           0.11.1     npx     ok    terminal         loadSession, session/list, session/resume              
stakpak             0.3.66     binary  ok    agent            loadSession                                            
```

## Method Probe Summary

| Method | Supported | Auth Required | Method Not Found | Other |
| --- | ---: | ---: | ---: | ---: |
| `session/list` | 13 | 1 | 11 | 1 |
| `session/fork` | 4 | 0 | 18 | 4 |
| `session/resume` | 7 | 1 | 16 | 2 |
| `session/stop` | 0 | 0 | 25 | 1 |
| `session/set_model` | 17 | 1 | 4 | 4 |
