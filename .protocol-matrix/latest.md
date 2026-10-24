# ACP Protocol Adaptation Matrix — 2026-10-24

_Generated at 2026-10-24T09:34:55+00:00_

- Agents in report: **37**
- Probed this run: **37**
- Reused unchanged versions: **0**
- `initialize` success: **36**
- `session/new` returned `auth_required`: **24**

Legend: `Capabilities` lists the capabilities advertised in the `initialize` response via `agentCapabilities` and `sessionCapabilities`.

```text
Agent               Version      Dist    Init      Auth                      Capabilities                                           
------------------  -----------  ------  --------  ------------------------  -------------------------------------------------------
amp-acp             0.10.0       binary  ok        terminal                  loadSession, session/resume                            
antigravity-acp     1.4.3        binary  ok        agent                     loadSession, session/list, session/resume              
auggie              0.36.0       npx     ok        terminal                  loadSession, session/list                              
autohand            0.2.1        npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
bob                 2.0.9        npx     ok        agent                     loadSession, session/list, session/resume              
claude-acp          0.95.0       npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
cline               3.0.73       npx     ok        agent                     loadSession                                            
codebuddy-code      2.174.0      npx     ok        agent                     loadSession                                            
codex-acp           2.2.2        npx     ok        agent                     loadSession, session/list, session/fork, session/resume
cortex-code         1.0.73       binary  proc_err  -                         -                                                      
corust-agent        0.6.0        binary  ok        agent                     -                                                      
cursor              2026.10.22   binary  ok        agent                     loadSession, session/list                              
devin               3000.11.205  binary  ok        agent, terminal           loadSession, session/list                              
dimcode             0.5.21       npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
dirac               0.5.23       npx     ok        agent, env_var, terminal  loadSession, session/resume                            
factory-droid       0.249.0      npx     ok        agent                     loadSession, session/list, session/resume              
gemini              0.65.0       npx     ok        agent                     loadSession                                            
github-copilot      1.561.0      npx     ok        agent                     loadSession, session/list                              
github-copilot-cli  1.0.103      npx     ok        terminal                  loadSession, session/list                              
glm-acp-agent       1.15.0       npx     ok        agent, env_var            loadSession, session/list, session/fork, session/resume
goose               1.56.0       binary  ok        agent                     loadSession, session/list                              
grok-build          1.0.70       npx     ok        agent                     loadSession, session/list, session/resume              
harn                0.10.175     binary  ok        agent                     loadSession, session/list, session/resume              
junie               3813.9.0     binary  ok        agent, terminal           loadSession, session/list, session/fork, session/resume
kilo                7.8.17       npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
kimchi              1.21.0       binary  ok        agent                     loadSession, session/list                              
kimi                1.52.0       binary  ok        terminal                  loadSession, session/list, session/resume              
minimax-code        0.2.7        npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
mistral-vibe        3.0.1        binary  ok        agent, terminal           loadSession, session/list, session/fork                
nova                1.1.59       npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
opencode            1.19.4       binary  ok        terminal                  loadSession, session/list, session/fork, session/resume
opencode-v2         2.1.4        binary  ok        terminal                  loadSession, session/list, session/fork, session/resume
pi-acp              0.0.34       npx     ok        terminal                  loadSession, session/list                              
poolside            1.0.16       binary  ok        terminal                  loadSession, session/list                              
qwen-code           0.26.0       npx     ok        agent                     loadSession, session/list, session/resume              
sigit               1.7.4        npx     ok        agent                     loadSession, session/list, session/fork, session/resume
stakpak             0.3.88       binary  ok        agent                     loadSession                                            
```

## Method Probe Summary

| Method | Supported | Auth Required | Method Not Found | Other |
| --- | ---: | ---: | ---: | ---: |
| `session/list` | 26 | 3 | 7 | 1 |
| `session/fork` | 11 | 3 | 18 | 5 |
| `session/resume` | 14 | 7 | 13 | 3 |
| `session/stop` | 0 | 0 | 34 | 3 |
| `session/set_model` | 17 | 2 | 13 | 5 |
