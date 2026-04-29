# ACP Protocol Adaptation Matrix — 2026-04-29

_Generated at 2026-04-29T07:35:46+00:00_

- Agents in report: **29**
- Probed this run: **29**
- Reused unchanged versions: **0**
- `initialize` success: **28**
- `session/new` returned `auth_required`: **19**

Legend: `Capabilities` lists the capabilities advertised in the `initialize` response via `agentCapabilities` and `sessionCapabilities`.

```text
Agent               Version     Dist    Init      Auth            Capabilities                                           
------------------  ----------  ------  --------  --------------  -------------------------------------------------------
agoragentic-acp     1.3.0       npx     ok        terminal        -                                                      
amp-acp             0.7.0       binary  ok        terminal        -                                                      
auggie              0.24.0      npx     ok        terminal        loadSession, session/list                              
autohand            0.2.1       npx     ok        terminal        loadSession, session/list, session/fork, session/resume
claude-acp          0.31.3      npx     ok        terminal        loadSession, session/list, session/fork, session/resume
cline               2.17.0      npx     ok        agent           loadSession                                            
codebuddy-code      2.94.1      npx     ok        agent           loadSession                                            
codex-acp           0.12.0      npx     ok        agent, env_var  loadSession, session/list                              
cortex-code         1.0.58      binary  proc_err  -               -                                                      
corust-agent        0.5.1       binary  ok        agent           -                                                      
crow-cli            0.1.20      binary  ok        terminal        loadSession                                            
cursor              2026.03.30  binary  ok        agent           loadSession                                            
dirac               0.3.1       npx     ok        agent           loadSession                                            
factory-droid       0.109.3     npx     ok        agent           loadSession, session/list, session/resume              
fast-agent          0.6.25      uvx     ok        agent           loadSession, session/list, session/resume              
gemini              0.39.1      npx     ok        agent           loadSession                                            
github-copilot      1.478.0     npx     ok        agent           loadSession, session/list                              
github-copilot-cli  1.0.38      npx     ok        terminal        loadSession, session/list                              
goose               1.32.0      binary  ok        agent           loadSession, session/list                              
kilo                7.2.25      npx     ok        terminal        loadSession, session/list, session/fork, session/resume
kimi                1.40.0      binary  ok        terminal        loadSession, session/list, session/resume              
mistral-vibe        2.8.1       binary  ok        terminal        loadSession, session/list                              
nova                1.1.0       npx     ok        terminal        loadSession, session/list, session/fork, session/resume
opencode            1.14.28     binary  ok        terminal        loadSession, session/list, session/fork, session/resume
pi-acp              0.0.26      npx     ok        terminal        loadSession, session/list                              
poolside            1.0.0       binary  ok        terminal        loadSession, session/list                              
qoder               0.2.3       npx     ok        agent, env_var  loadSession, session/list                              
qwen-code           0.15.4      npx     ok        agent           loadSession, session/list, session/resume              
stakpak             0.3.77      binary  ok        agent           loadSession                                            
```

## Method Probe Summary

| Method | Supported | Auth Required | Method Not Found | Other |
| --- | ---: | ---: | ---: | ---: |
| `session/list` | 16 | 2 | 9 | 2 |
| `session/fork` | 7 | 0 | 20 | 2 |
| `session/resume` | 7 | 2 | 19 | 1 |
| `session/stop` | 0 | 0 | 28 | 1 |
| `session/set_model` | 18 | 1 | 3 | 7 |
