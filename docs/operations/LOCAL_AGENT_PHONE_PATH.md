# Local agent phone path — 2026-08-27

## Route and invocation

Select Josie in the existing Open WebUI instance. Send `Delegate Local: <complete task
and acceptance criteria>`. The original `Delegate Local Code:` form is still supported.
The short prefix is normalized only at the existing conversation-control boundary;
`josie/local_code.py` is unchanged.

Open WebUI's existing `josie_exact_tool_response` filter → authenticated existing
conversation-control `/v1/delegate/local-code` → `delegate_local_code` → native OpenCode
1.18.23 → Ollama 0.32.5 → `josie-qual-qwen3:8b-32k` → C:\Josie.
No Codex or cloud model/API is used by this route. Existing Codex routes remain unchanged.

Receipts: `C:\Josie\data\private\local-code-jobs`. Status-only recovery:
`Delegate Local status: <job-id>`. This reads the existing receipt without rerunning.
Do not resubmit an uncertain job with a new ID. The existing shared lock and 900s timeout
are unchanged. Repository/authority protections and the actual-result adapter are unchanged.

The native Open WebUI stream hook suppresses conversational-model chunks for ONLY local
delegation/status requests. Those requests use streaming at the request level so this
hook always applies. Normal chats and Codex routes are passed through unchanged.
The outlet shows `JOSIE LOCAL CODE — PENDING` while waiting, then replaces it with
`JOSIE LOCAL CODE — ACTUAL RESULT` or an explicit unavailable result. Raw model commentary
is not execution evidence. No global streaming/configuration setting is changed.

Qwen3 currently runs on CPU. The reference qualification took 735.81s; expect substantial
latency, potentially close to the 15-minute timeout. Closing the browser does not establish
whether a job stopped; use its receipt ID to check rather than sending another request.

## Persistent deployment changes

- Updated only the source of the existing `josie_exact_tool_response` function in the
  Open WebUI persistent database, using the existing installer. Other function fields
  were verified unchanged. No users, conversations, model settings, valves, or global
  configuration were replaced.
- Restarted only the existing Open WebUI container and existing conversation-control
  process via `\Josie\Josie Conversation Control`; no new service/container/port.
- Open WebUI was restarted twice: initial route deployment, then native stream suppression.
  Conversation-control was restarted once. The adapter itself was not changed.
- Pinned native OpenCode `shell` to `C:/Program Files/Git/bin/bash.exe`. The initial live
  service selected Windows PowerShell 5.1, which rejected `&&`, unlike the direct
  qualification environment. `OPENCODE_GIT_BASH_PATH` alone did not force shell selection.
  This single native config setting removes environment-dependent shell selection without
  adding a dependency, changing global PATH, or altering the adapter.
  Official configuration: https://opencode.ai/docs/config/#shell . Version-specific
  selection code: https://github.com/anomalyco/opencode/blob/v1.18.23/packages/core/src/shell.ts .
  The runtime log independently confirmed the difference: qualification used the
  conductor's PowerShell 7; the first service job used Windows PowerShell 5.1;
  the post-fix service job logged `shell="C:/Program Files/Git/bin/bash.exe"`.
  Thus the deployed path no longer relies incidentally on the conductor's bundled shell.
- Open WebUI image pin remained v0.11.1; no upgrade, Compose recreation, firewall or
  Tailscale change. Local and Tailscale `/health` endpoints were healthy after restart.
- Pre-deployment counts: 1 user, 53 chats, 1 model, 9 config records. Identical counts
  were confirmed after the first restart, before the new smoke-test chat was submitted.
- Original filter backup (inside the existing persistent Open WebUI volume):
  `/app/backend/data/josie-filter-before-delegate-6e186570c5294cc7ffc118244d5346784a2d20bd663be30e7300747acbad0d59.json`.
  Preserve this backup. It contains the function definition, not a replacement database.

## Recovery

Proven-state annotated tag: `local-agent-runtime-proven-20260827`, resolving to
`04f395d56d3f5eb3371469ae875a348d28799ead`. It was created without moving existing refs.
After ensuring no delegation is running and preserving any later uncommitted work,
the exact command to return the source to a new recovery branch is:

```powershell
git -C C:\Josie switch -c recover-local-runtime-20260827 local-agent-runtime-proven-20260827
```

The pre-existing Compose edit is unchanged by this task and is compatible with the
recovery commit. If Git reports conflicts or the recovery branch already exists, stop
and inspect; do not force, reset, or discard work. Git recovery does not itself roll
back Open WebUI's stored filter. Restore that separately with:

```powershell
@'
import asyncio, json, os, sys
from pathlib import Path
sys.path.insert(0, '/app/backend')
if not os.environ.get('WEBUI_SECRET_KEY'):
    os.environ['WEBUI_SECRET_KEY'] = Path('/app/backend/.webui_secret_key').read_text().strip()
from open_webui.models.functions import Functions
async def restore():
    path = Path('/app/backend/data/josie-filter-before-delegate-6e186570c5294cc7ffc118244d5346784a2d20bd663be30e7300747acbad0d59.json')
    prior = json.loads(path.read_text())
    saved = await Functions.update_function_by_id('josie_exact_tool_response', {'content': prior['content']})
    assert saved.content == prior['content']
    print('Original filter source restored; other fields preserved.')
asyncio.run(restore())
'@ | docker.exe exec -i josie-open-webui-1 python -
if ($LASTEXITCODE -ne 0) { throw 'Restore failed; inspect before restarting.' }
docker.exe restart josie-open-webui-1
& C:\Josie\scripts\Stop-JosieConversationControl.ps1
Start-ScheduledTask -TaskPath '\Josie\' -TaskName 'Josie Conversation Control'
```

Never run restarts during an active delegated job. Health checks:
`http://127.0.0.1:8790/health`, `http://127.0.0.1:3000/health`, and
`https://refurb.tail0ab4d2.ts.net/health`. Do not expose the control endpoint directly.

## Verification

Baseline 149/149. Final suite: **157/157 passed in 39.856s** after deployment and both
live smoke jobs. Eight focused tests cover aliases, status, draft suppression, unchanged
Codex stream behavior, request-scoped streaming and native shell configuration.
Compose, the local runtime adapter and Codex delegation adapter hashes are unchanged.
Final persistent counts: 1 user, 55 chats (two new smoke chats), 1 model, 9 config records.
Tailscale health passed and the shared delegation lock was absent after completion.

Initial live UI smoke: `openwebui-localcode-1bb25773e29dec4f1fa07370c916cbac`.
The request was submitted through the real signed-in Josie chat, not directly to Python.
It reached OpenCode/Ollama, encountered the PowerShell 5.1 separator error, recovered with
a second tool call, and returned actual Python 3.12.10 and Git status to the chat.
Elapsed 897.72s, final response present, no timeout, no files changed. Receipt status was
honestly `failed` because the first tool had exit 1; the recovered tool had exit 0.

That run also exposed conversational draft text falsely claiming another Python version
and branch while the job was pending. Native stream suppression fixed this presentation
bug. Post-fix live UI inspection showed only the pending heading/job ID and no invented
output. The second live smoke ID is
`openwebui-localcode-940edd31320ab8d03d99c37ea6f72c97` (single Python-version command).

Post-fix smoke **completed in 495.2s**: one genuine bash call,
`.venv/Scripts/python.exe --version`, actual output `Python 3.12.10`, tool and process
exit 0, no timeout, no changed files, and a genuine final response. The actual-result
heading and completed receipt were observed in the real signed-in Josie chat at
`/c/73788322-8898-4ae2-a48d-850f1d1ebf62`. No Codex/cloud runtime was used.
This is a host-browser smoke through the real UI; Dustin's phone-originated test remains
the next step, not something this task claims to have performed.
After browser reload, the same chat still displayed the completed actual result,
correct receipt ID and Python 3.12.10 output.

## One phone test

Select Josie and paste this one request. The fixed new filename intentionally refuses
to overwrite an existing file. Its assertions are the deterministic test; no package
installation, Git commit or production-data change is requested.

```text
Delegate Local: Use bash in C:/Josie to run exactly this command:
.venv/Scripts/python.exe -c "from pathlib import Path; import sys; d=Path('docs/operations'); assert d.is_dir(); print('Inspected:',d.resolve()); p=d/'phone-local-proof-20260827.txt'; assert not p.exists(); p.write_text('JOSIE_PHONE_OK'); assert p.read_text()=='JOSIE_PHONE_OK'; print('VERIFIED:',p.resolve(),p.read_text()); print(sys.version)"
Acceptance: execute the command, report its actual output and receipt ID, and leave the fixture for verification. Do not change any other files or stage/commit anything.
```
