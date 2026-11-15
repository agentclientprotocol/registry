# ACP Protocol Adaptation Matrix — 2026-10-10

_Generated at 2026-10-10T11:12:05+00:00_

- Agents in report: **35**
- Probed this run: **35**
- Reused unchanged versions: **0**
- `initialize` success: **34**
- `session/new` returned `auth_required`: **23**

Legend: `Capabilities` lists the capabilities advertised in the `initialize` response via `agentCapabilities` and `sessionCapabilities`.

```text
Agent               Version     Dist    Init      Auth                      Capabilities                                           
------------------  ----------  ------  --------  ------------------------  -------------------------------------------------------
amp-acp             0.10.0      binary  ok        terminal                  loadSession, session/resume                            
antigravity-acp     1.3.0       binary  ok        agent                     loadSession, session/list, session/resume              
auggie              0.36.0      npx     ok        terminal                  loadSession, session/list                              
autohand            0.2.1       npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
claude-acp          0.89.1      npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
cline               3.0.70      npx     ok        agent                     loadSession                                            
codebuddy-code      2.164.0     npx     ok        agent                     loadSession                                            
codex-acp           2.2.2       npx     ok        agent                     loadSession, session/list, session/fork, session/resume
cortex-code         1.0.73      binary  proc_err  -                         -                                                      
corust-agent        0.6.0       binary  ok        agent                     -                                                      
cursor              2026.10.01  binary  ok        agent                     loadSession, session/list                              
devin               3000.11.3   binary  ok        agent, terminal           loadSession, session/list                              
dimcode             0.5.16      npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
dirac               0.5.18      npx     ok        agent, env_var, terminal  loadSession, session/resume                            
factory-droid       0.238.0     npx     ok        agent                     loadSession, session/list, session/resume              
gemini              0.63.0      npx     ok        agent                     loadSession                                            
github-copilot      1.552.0     npx     ok        agent                     loadSession, session/list                              
github-copilot-cli  1.0.95      npx     ok        terminal                  loadSession, session/list                              
glm-acp-agent       1.14.0      npx     ok        agent, env_var            loadSession, session/list, session/fork, session/resume
goose               1.54.0      binary  ok        agent                     loadSession, session/list                              
grok-build          1.0.51      npx     ok        agent                     loadSession, session/list, session/resume              
harn                0.10.160    binary  ok        agent                     loadSession, session/list, session/resume              
junie               3579.5.0    binary  ok        agent                     loadSession, session/list, session/fork, session/resume
kilo                7.8.8       npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
kimchi              1.9.1       binary  ok        agent                     loadSession, session/list                              
kimi                1.52.0      binary  ok        terminal                  loadSession, session/list, session/resume              
minimax-code        0.2.7       npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
mistral-vibe        2.26.1      binary  ok        agent, terminal           loadSession, session/list, session/fork                
nova                1.1.51      npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
opencode            1.18.35     binary  ok        terminal                  loadSession, session/list, session/fork, session/resume
pi-acp              0.0.34      npx     ok        terminal                  loadSession, session/list                              
poolside            1.0.16      binary  ok        terminal                  loadSession, session/list                              
qwen-code           0.25.0      npx     ok        agent                     loadSession, session/list, session/resume              
sigit               1.6.6       npx     ok        agent                     loadSession, session/list, session/fork, session/resume
stakpak             0.3.88      binary  ok        agent                     loadSession                                            
```

## Method Probe Summary

| Method | Supported | Auth Required | Method Not Found | Other |
| --- | ---: | ---: | ---: | ---: |
| `session/list` | 23 | 4 | 7 | 1 |
| `session/fork` | 10 | 3 | 18 | 4 |
| `session/resume` | 12 | 7 | 14 | 2 |
| `session/stop` | 0 | 0 | 32 | 3 |
| `session/set_model` | 17 | 2 | 11 | 5 |
