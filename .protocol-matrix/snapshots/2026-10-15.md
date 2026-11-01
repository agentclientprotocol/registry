# ACP Protocol Adaptation Matrix — 2026-10-15

_Generated at 2026-10-15T09:58:58+00:00_

- Agents in report: **36**
- Probed this run: **36**
- Reused unchanged versions: **0**
- `initialize` success: **35**
- `session/new` returned `auth_required`: **23**

Legend: `Capabilities` lists the capabilities advertised in the `initialize` response via `agentCapabilities` and `sessionCapabilities`.

```text
Agent               Version     Dist    Init      Auth                      Capabilities                                           
------------------  ----------  ------  --------  ------------------------  -------------------------------------------------------
amp-acp             0.10.0      binary  ok        terminal                  loadSession, session/resume                            
antigravity-acp     1.4.0       binary  ok        agent                     loadSession, session/list, session/resume              
auggie              0.36.0      npx     ok        terminal                  loadSession, session/list                              
autohand            0.2.1       npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
bob                 2.0.7       npx     ok        agent                     loadSession, session/list, session/resume              
claude-acp          0.90.0      npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
cline               3.0.71      npx     ok        agent                     loadSession                                            
codebuddy-code      2.167.0     npx     ok        agent                     loadSession                                            
codex-acp           2.2.2       npx     ok        agent                     loadSession, session/list, session/fork, session/resume
cortex-code         1.0.73      binary  proc_err  -                         -                                                      
corust-agent        0.6.0       binary  ok        agent                     -                                                      
cursor              2026.10.14  binary  ok        agent                     loadSession, session/list                              
devin               3000.11.92  binary  ok        agent, terminal           loadSession, session/list                              
dimcode             0.5.18      npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
dirac               0.5.21      npx     ok        agent, env_var, terminal  loadSession, session/resume                            
factory-droid       0.242.0     npx     ok        agent                     loadSession, session/list, session/resume              
gemini              0.64.0      npx     ok        agent                     loadSession                                            
github-copilot      1.554.0     npx     ok        agent                     loadSession, session/list                              
github-copilot-cli  1.0.98      npx     ok        terminal                  loadSession, session/list                              
glm-acp-agent       1.15.0      npx     ok        agent, env_var            loadSession, session/list, session/fork, session/resume
goose               1.54.0      binary  ok        agent                     loadSession, session/list                              
grok-build          1.0.60      npx     ok        agent                     loadSession, session/list, session/resume              
harn                0.10.165    binary  ok        agent                     loadSession, session/list, session/resume              
junie               3659.4.0    binary  ok        agent, terminal           loadSession, session/list, session/fork, session/resume
kilo                7.8.8       npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
kimchi              1.13.0      binary  ok        agent                     loadSession, session/list                              
kimi                1.52.0      binary  ok        terminal                  loadSession, session/list, session/resume              
minimax-code        0.2.7       npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
mistral-vibe        2.26.1      binary  ok        agent, terminal           loadSession, session/list, session/fork                
nova                1.1.53      npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
opencode            1.19.0      binary  ok        terminal                  loadSession, session/list, session/fork, session/resume
pi-acp              0.0.34      npx     ok        terminal                  loadSession, session/list                              
poolside            1.0.16      binary  ok        terminal                  loadSession, session/list                              
qwen-code           0.25.1      npx     ok        agent                     loadSession, session/list, session/resume              
sigit               1.6.9       npx     ok        agent                     loadSession, session/list, session/fork, session/resume
stakpak             0.3.88      binary  ok        agent                     loadSession                                            
```

## Method Probe Summary

| Method | Supported | Auth Required | Method Not Found | Other |
| --- | ---: | ---: | ---: | ---: |
| `session/list` | 24 | 4 | 7 | 1 |
| `session/fork` | 10 | 3 | 18 | 5 |
| `session/resume` | 13 | 7 | 13 | 3 |
| `session/stop` | 0 | 0 | 33 | 3 |
| `session/set_model` | 17 | 2 | 12 | 5 |
