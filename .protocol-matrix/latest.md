# ACP Protocol Adaptation Matrix — 2026-11-14

_Generated at 2026-11-14T12:13:26+00:00_

- Agents in report: **42**
- Probed this run: **42**
- Reused unchanged versions: **0**
- `initialize` success: **41**
- `session/new` returned `auth_required`: **27**

Legend: `Capabilities` lists the capabilities advertised in the `initialize` response via `agentCapabilities` and `sessionCapabilities`.

```text
Agent               Version     Dist    Init      Auth                      Capabilities                                           
------------------  ----------  ------  --------  ------------------------  -------------------------------------------------------
amp-acp             0.12.0      binary  ok        terminal                  loadSession, session/list, session/resume              
antigravity-acp     1.5.0       binary  ok        agent                     loadSession, session/list, session/resume              
auggie              0.37.0      npx     ok        terminal                  loadSession, session/list                              
autohand            0.9.11      binary  ok        terminal                  loadSession, session/list, session/fork, session/resume
bob                 2.1.0       npx     ok        agent                     loadSession, session/list, session/resume              
claude-acp          0.107.0     npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
cline               3.0.74      npx     ok        agent                     loadSession                                            
codebuddy-code      2.184.0     npx     ok        agent                     loadSession                                            
codex-acp           2.6.0       npx     ok        agent                     loadSession, session/list, session/fork, session/resume
cortex-code         1.0.73      binary  proc_err  -                         -                                                      
corust-agent        0.6.0       binary  ok        agent                     -                                                      
crow-cli            0.1.49      binary  ok        terminal                  loadSession, session/list, session/fork                
cursor              2026.11.13  binary  ok        agent                     loadSession, session/list                              
devin               3000.12.57  binary  ok        agent, terminal           loadSession, session/list                              
dimcode             0.5.28      npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
dirac               0.6.0       npx     ok        agent, env_var, terminal  loadSession, session/list, session/fork, session/resume
factory-droid       1.12.1      npx     ok        agent                     loadSession, session/list, session/fork, session/resume
gemini              0.68.0      npx     ok        agent                     loadSession                                            
github-copilot      1.570.0     npx     ok        agent                     loadSession, session/list                              
github-copilot-cli  1.0.112     npx     ok        terminal                  loadSession, session/list                              
glm-acp-agent       1.17.1      npx     ok        agent, env_var            loadSession, session/list, session/fork, session/resume
goose               1.59.1      binary  ok        agent                     loadSession, session/list                              
grok-build          1.0.85      npx     ok        agent                     loadSession, session/list, session/resume              
harn                0.10.197    binary  ok        agent                     loadSession, session/list, session/resume              
junie               4020.10.0   binary  ok        agent, terminal           loadSession, session/list, session/fork, session/resume
kilo                7.8.27      npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
kimchi              1.34.3      binary  ok        agent                     loadSession, session/list, session/resume              
kimi                1.52.0      binary  ok        terminal                  loadSession, session/list, session/resume              
kimi-code           2.6.2       npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
kiro                3.0.0       binary  ok        terminal                  -                                                      
minimax-code        0.2.7       npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
mistral-vibe        3.1.1       binary  ok        agent, terminal           loadSession, session/list, session/fork                
muse-code           1.4.14      binary  ok        agent                     loadSession, session/list, session/resume              
nova                1.1.65      npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
opencode            2.3.0       binary  ok        terminal                  loadSession, session/list, session/fork, session/resume
opencode-v2         2.3.0       binary  ok        terminal                  loadSession, session/list, session/fork, session/resume
pi-acp              0.0.34      npx     ok        terminal                  loadSession, session/list                              
poolside            1.0.16      binary  ok        terminal                  loadSession, session/list                              
qoder               1.1.89      npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
qwen-code           0.27.3      npx     ok        agent                     loadSession, session/list, session/resume              
sigit               1.7.10      npx     ok        agent                     loadSession, session/list, session/fork, session/resume
stakpak             0.3.88      binary  ok        agent                     loadSession                                            
```

## Method Probe Summary

| Method | Supported | Auth Required | Method Not Found | Other |
| --- | ---: | ---: | ---: | ---: |
| `session/list` | 30 | 5 | 5 | 2 |
| `session/fork` | 13 | 7 | 17 | 5 |
| `session/resume` | 17 | 11 | 11 | 3 |
| `session/stop` | 0 | 1 | 38 | 3 |
| `session/set_model` | 17 | 4 | 17 | 4 |
