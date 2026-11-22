# ACP Protocol Adaptation Matrix — 2026-11-22

_Generated at 2026-11-22T13:23:47+00:00_

- Agents in report: **43**
- Probed this run: **43**
- Reused unchanged versions: **0**
- `initialize` success: **42**
- `session/new` returned `auth_required`: **27**

Legend: `Capabilities` lists the capabilities advertised in the `initialize` response via `agentCapabilities` and `sessionCapabilities`.

```text
Agent               Version        Dist    Init      Auth                      Capabilities                                           
------------------  -------------  ------  --------  ------------------------  -------------------------------------------------------
amp-acp             0.13.0         binary  ok        terminal                  loadSession, session/list, session/resume              
antigravity-acp     1.5.2          binary  ok        agent                     loadSession, session/list, session/resume              
auggie              0.37.0         npx     ok        terminal                  loadSession, session/list                              
autohand            0.9.12         binary  ok        terminal                  loadSession, session/list, session/fork, session/resume
bob                 2.1.0          npx     ok        agent                     loadSession, session/list, session/resume              
claude-acp          0.109.1        npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
cline               3.0.75         npx     ok        agent                     loadSession                                            
codebuddy-code      2.185.0        npx     ok        agent                     loadSession                                            
codex-acp           2.9.0          npx     ok        agent                     loadSession, session/list, session/fork, session/resume
cortex-code         1.0.73         binary  proc_err  -                         -                                                      
corust-agent        0.6.0          binary  ok        agent                     -                                                      
crow-cli            0.1.49         binary  ok        terminal                  loadSession, session/list, session/fork                
cursor              2026.11.19     binary  ok        agent                     loadSession, session/list                              
devin               3000.14.30821  binary  ok        agent, terminal           loadSession, session/list                              
dimcode             0.5.30         npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
dirac               0.6.1          npx     ok        agent, env_var, terminal  loadSession, session/list, session/fork, session/resume
factory-droid       1.17.2         npx     ok        agent                     loadSession, session/list, session/fork, session/resume
fast-agent          0.10.64        uvx     ok        agent                     loadSession, session/list, session/resume              
gemini              0.70.0         npx     ok        agent                     loadSession                                            
github-copilot      1.573.0        npx     ok        agent                     loadSession, session/list                              
github-copilot-cli  1.0.114        npx     ok        terminal                  loadSession, session/list                              
glm-acp-agent       1.17.1         npx     ok        agent, env_var            loadSession, session/list, session/fork, session/resume
goose               1.60.2         binary  ok        agent                     loadSession, session/list                              
grok-build          1.0.93         npx     ok        agent                     loadSession, session/list, session/resume              
harn                0.10.202       binary  ok        agent                     loadSession, session/list, session/resume              
junie               4100.11.0      binary  ok        agent, terminal           loadSession, session/list, session/fork, session/resume
kilo                7.8.32         npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
kimchi              1.37.5         binary  ok        agent                     loadSession, session/list, session/resume              
kimi                1.52.0         binary  ok        terminal                  loadSession, session/list, session/resume              
kimi-code           2.7.2          npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
kiro                3.0.0          binary  ok        terminal                  -                                                      
minimax-code        0.7.9          npx     ok        env_var, terminal         loadSession, session/list, session/fork, session/resume
mistral-vibe        3.1.1          binary  ok        agent, terminal           loadSession, session/list, session/fork                
muse-code           1.4.24         binary  ok        agent                     loadSession, session/list, session/resume              
nova                1.1.68         npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
opencode            2.3.2          binary  ok        terminal                  loadSession, session/list, session/fork, session/resume
opencode-v2         2.3.2          binary  ok        terminal                  loadSession, session/list, session/fork, session/resume
pi-acp              0.0.35         npx     ok        terminal                  loadSession, session/list                              
poolside            1.0.16         binary  ok        terminal                  loadSession, session/list                              
qoder               1.1.95         npx     ok        terminal                  loadSession, session/list, session/fork, session/resume
qwen-code           0.28.3         npx     ok        agent                     loadSession, session/list, session/resume              
sigit               1.7.10         npx     ok        agent                     loadSession, session/list, session/fork, session/resume
stakpak             0.3.88         binary  ok        agent                     loadSession                                            
```

## Method Probe Summary

| Method | Supported | Auth Required | Method Not Found | Other |
| --- | ---: | ---: | ---: | ---: |
| `session/list` | 31 | 5 | 5 | 2 |
| `session/fork` | 13 | 7 | 18 | 5 |
| `session/resume` | 18 | 11 | 11 | 3 |
| `session/stop` | 0 | 1 | 39 | 3 |
| `session/set_model` | 17 | 4 | 18 | 4 |
