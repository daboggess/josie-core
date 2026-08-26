# Josie Maintainer Mode 0.1

Maintainer Mode is a local, fail-closed extension of Josie's existing conversation-control service. Open WebUI remains the front door, local Ollama remains the default conversation model, and Codex/Gemini remain optional advisory seats.

## Exact write request

Use one explicit, bounded replacement per request:

```text
Maintainer Mode: in docs/operations/example.md replace "exact old text" with "exact new text".
```

Josie's deterministic filter—not the local model—extracts those exact fields. The control plane then requires a clean tree, creates a `maintenance/` branch, changes only the named existing file, records the diff, runs the full suite, and commits locally only after the tests pass. It never pushes.

If a focused test is needed, use the read-only test tool first. Maintainer Mode 0.1 always runs the complete suite before its write commit.

## Read-only requests

Ask Josie explicitly to:

- report `Maintainer Mode status`;
- read a relative project file;
- search the Josie repository for a filename or text;
- show Git status or a Git diff;
- run the approved Josie test suite.

There is no arbitrary-shell tool. Approved Python and PowerShell operations are fixed command IDs in the local policy; model-supplied command text is rejected.

## Protected boundary

Credentials, environment/authentication stores, Constitution/identity/authority/security rules, policy and control-plane files, startup/security infrastructure, packages, containers, databases, network exposure, Tailscale, permissions, destructive changes, Git history rewriting, recovery tags, and remote push are outside autonomous authority. A request that reaches a protected path stops with `approval_required`; consultant advice cannot override that result.

## Rollback

Failed tests restore the original bytes and return to the base branch automatically. A completed job records its maintenance branch, base commit, final commit, and a non-rewriting rollback instruction. To reverse a completed change, use the authenticated rollback endpoint or run the recorded `git revert <commit>` on the recorded maintenance branch.

## Audit

Josie's existing SQLite database stores the request ID, exact user request, operation, target, files read/changed, command records, branch/checkpoint, diff summary, tests, consultant evidence references, final commit or rollback, approval state, and ordered maintenance events.
