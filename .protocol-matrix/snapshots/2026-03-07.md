# ACP Protocol Adaptation Matrix — 2026-03-07

_Generated at 2026-03-07T21:12:16+00:00_

- Agents in report: **27**
- Probed this run: **27**
- Reused unchanged versions: **0**
- `initialize` success: **15**
- `session/new` returned `auth_required`: **12**

Legend: `Capabilities` lists the capabilities advertised in the `initialize` response via `agentCapabilities` and `sessionCapabilities`.

```text
Agent               Version    Dist    Init      Auth      Capabilities                                           
------------------  ---------  ------  --------  --------  -------------------------------------------------------
amp-acp             0.7.0      binary  proc_err  -         -                                                      
auggie              0.18.1     npx     ok        terminal  loadSession, session/list                              
autohand            0.2.1      npx     ok        terminal  loadSession, session/list, session/fork, session/resume
claude-acp          0.20.2     npx     ok        terminal  loadSession, session/list, session/fork, session/resume
cline               2.6.0      npx     ok        agent     loadSession                                            
codebuddy-code      2.55.1     npx     ok        agent     loadSession                                            
codex-acp           0.9.5      npx     ok        agent     loadSession, session/list                              
corust-agent        0.3.7      binary  proc_err  -         -                                                      
crow-cli            0.1.12     uvx     proc_err  -         -                                                      
cursor              0.1.0      binary  proc_err  -         -                                                      
dimcode             0.0.13     npx     ok        agent     loadSession, session/list, session/resume              
factory-droid       0.69.0     npx     ok        agent     loadSession, session/list, session/resume              
gemini              0.32.1     npx     ok        agent     loadSession                                            
github-copilot      1.448.0    npx     ok        agent     loadSession                                            
github-copilot-cli  0.0.422    npx     ok        terminal  loadSession, session/list                              
goose               1.27.1     binary  proc_err  -         -                                                      
junie               888.117.0  npx     proc_err  -         -                                                      
kilo                7.0.39     npx     ok        terminal  loadSession, session/list, session/fork, session/resume
kimi                1.17.0     binary  proc_err  -         -                                                      
minion-code         0.1.39     uvx     ok        agent     -                                                      
mistral-vibe        2.3.0      binary  proc_err  -         -                                                      
nova                1.0.66     npx     no        -         -                                                      
opencode            1.2.20     binary  proc_err  -         -                                                      
pi-acp              0.0.21     npx     ok        terminal  loadSession, session/list                              
qoder               0.1.29     npx     ok        terminal  loadSession                                            
qwen-code           0.11.1     npx     proc_err  -         -                                                      
stakpak             0.3.66     binary  proc_err  -         -                                                      
```

## Method Probe Summary

| Method | Supported | Auth Required | Method Not Found | Other |
| --- | ---: | ---: | ---: | ---: |
| `session/list` | 7 | 1 | 7 | 12 |
| `session/fork` | 3 | 0 | 12 | 12 |
| `session/resume` | 4 | 1 | 10 | 12 |
| `session/stop` | 0 | 0 | 15 | 12 |
| `session/set_model` | 9 | 0 | 3 | 15 |
