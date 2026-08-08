# Sophie and Bernie handoffs

Josie does not call ChatGPT or Gemini APIs for model coordination. Instead, she
creates local drafts that Dustin or Codex Remote may deliberately relay through
an already available subscription or free-tier chat surface.

This keeps the default cloud lock intact:

- API budget is fixed at zero cents in SQLite;
- manual relay is always required;
- creating or exporting a draft performs no external activity;
- there is no `send`, `submit`, provider-call, or automatic comparison command;
- obvious API keys, bearer tokens, and private keys are rejected before storage;
- a recorded answer is marked untrusted and cannot queue or execute an action;
- paid or metered API use requires a separate future approval and code change.

## Local GUI

```text
ask Sophie review Josie's latest health report
ask Bernie compare two CPU-safe model-routing designs
handoffs
record handoff answer 1: manually relayed response text
```

The first two commands save drafts only. The last command records text supplied
by Dustin; it does not contact a provider.

## Command line

```powershell
cd C:\Josie
.\.venv\Scripts\python.exe .\core.py handoffs create sophie "Review Josie's latest health report"
.\.venv\Scripts\python.exe .\core.py handoffs create bernie "Compare two CPU-safe designs"
.\.venv\Scripts\python.exe .\core.py handoffs list
.\.venv\Scripts\python.exe .\core.py handoffs export 1
.\.venv\Scripts\python.exe .\core.py handoffs answer 1 "Manually relayed response"
```

Export writes a secret-screened JSON file under
`D:\Josie-Storage\handoffs\outbox`. Tell Codex Remote to check Josie's local
handoffs when you want Sophie to pick one up. For Bernie, manually paste the
draft into Gemini only when you choose to do so. No API credit, billing setting,
or cloud-spend flag is changed by this workflow.
