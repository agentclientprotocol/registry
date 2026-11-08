# ACP Protocol Adaptation Matrix — 2026-11-07

_Generated at 2026-11-07T11:45:21+00:00_

- Agents in report: **40**
- Probed this run: **40**
- Reused unchanged versions: **0**
- `initialize` success: **39**
- `session/new` returned `auth_required`: **25**

Legend: `Capabilities` lists the capabilities advertised in the `initialize` response via `agentCapabilities` and `sessionCapabilities`.

```text
Agent               Version     Dist    Init      Auth                      Capabilities                                           
------------------  ----------  ------  --------  ------------------------  -------------------------------------------------------
amp-acp             0.12.0      binary  ok        terminal                  loadSession, session/list, session/resume              
antigravity-acp     1.4.5       binary  ok        agent                     loadSession, session/list, session/resume              
auggie              0.37.0      npx     ok        terminal                  loadSession, session/list                              
autohand            0.9.10      binary  ok        terminal                  loadSession, session/list, session/fork, session/resume
bob                 2.0.9       npx     ok        agent                     loadSession, session/list, session/resume              
claude-acp          0.101.0     npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
cline               3.0.74      npx     ok        agent                     loadSession                                            
codebuddy-code      2.181.0     npx     ok        agent                     loadSession                                            
codex-acp           2.5.0       npx     ok        agent                     loadSession, session/list, session/fork, session/resume
cortex-code         1.0.73      binary  proc_err  -                         -                                                      
corust-agent        0.6.0       binary  ok        agent                     -                                                      
crow-cli            0.1.49      binary  ok        terminal                  loadSession, session/list, session/fork                
cursor              2026.11.05  binary  ok        agent                     loadSession, session/list                              
devin               3000.12.17  binary  ok        agent, terminal           loadSession, session/list                              
dimcode             0.5.24      npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
dirac               0.5.24      npx     ok        agent, env_var, terminal  loadSession, session/list, session/fork, session/resume
factory-droid       1.6.0       npx     ok        agent                     loadSession, session/list, session/fork, session/resume
gemini              0.67.0      npx     ok        agent                     loadSession                                            
github-copilot      1.566.0     npx     ok        agent                     loadSession, session/list                              
github-copilot-cli  1.0.107     npx     ok        terminal                  loadSession, session/list                              
glm-acp-agent       1.17.0      npx     ok        agent, env_var            loadSession, session/list, session/fork, session/resume
goose               1.57.0      binary  ok        agent                     loadSession, session/list                              
grok-build          1.0.78      npx     ok        agent                     loadSession, session/list, session/resume              
harn                0.10.190    binary  ok        agent                     loadSession, session/list, session/resume              
junie               3959.5.0    binary  ok        agent, terminal           loadSession, session/list, session/fork, session/resume
kilo                7.8.27      npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
kimchi              1.29.0      binary  ok        agent                     loadSession, session/list, session/resume              
kimi                1.52.0      binary  ok        terminal                  loadSession, session/list, session/resume              
kimi-code           2.5.2       npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
kiro                3.0.0       binary  ok        terminal                  -                                                      
minimax-code        0.2.7       npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
mistral-vibe        3.1.0       binary  ok        agent, terminal           loadSession, session/list, session/fork                
nova                1.1.64      npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
opencode            2.2.6       binary  ok        terminal                  loadSession, session/list, session/fork, session/resume
opencode-v2         2.2.6       binary  ok        terminal                  loadSession, session/list, session/fork, session/resume
pi-acp              0.0.34      npx     ok        terminal                  loadSession, session/list                              
poolside            1.0.16      binary  ok        terminal                  loadSession, session/list                              
qwen-code           0.26.9      npx     ok        agent                     loadSession, session/list, session/resume              
sigit               1.7.8       npx     ok        agent                     loadSession, session/list, session/fork, session/resume
stakpak             0.3.88      binary  ok        agent                     loadSession                                            
```

## Method Probe Summary

| Method | Supported | Auth Required | Method Not Found | Other |
| --- | ---: | ---: | ---: | ---: |
| `session/list` | 30 | 4 | 5 | 1 |
| `session/fork` | 13 | 6 | 16 | 5 |
| `session/resume` | 17 | 9 | 11 | 3 |
| `session/stop` | 0 | 1 | 36 | 3 |
| `session/set_model` | 17 | 3 | 16 | 4 |
