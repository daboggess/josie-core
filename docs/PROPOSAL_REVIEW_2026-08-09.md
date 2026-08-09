# Proposal review queue — 2026-08-09

No decision in this document executes an action. Proposal acceptance records a
human review decision only; it still queues and executes nothing.

## Recommended cleanup

The six external records were created while validating the Open WebUI bridge,
phone access, grounding, and duplicate suppression. They are test artifacts and
can be rejected as a group:

- External 1 — Open WebUI global-tool acceptance test.
- External 2 — Phone test successful.
- External 3 — Grounded reply validation.
- External 4 — Phone test successful.
- External 5 — Phone test successful.
- External 6 — Duplicate suppression live validation.

The two local-model records were generated during the governed planner test:

- Model 1 proposed a review-only health check; no check ran.
- Model 2 correctly refused a request outside the handler allowlist.

Both are historical test artifacts and can also be rejected after Dustin
confirms the cleanup.

## Exact local commands

Run only after Dustin explicitly approves rejecting these records:

```powershell
cd C:\Josie
.\.venv\Scripts\python.exe .\core.py proposals review external 1 reject --reason "Acceptance test only"
.\.venv\Scripts\python.exe .\core.py proposals review external 2 reject --reason "Phone acceptance test only"
.\.venv\Scripts\python.exe .\core.py proposals review external 3 reject --reason "Grounding acceptance test only"
.\.venv\Scripts\python.exe .\core.py proposals review external 4 reject --reason "Phone acceptance test only"
.\.venv\Scripts\python.exe .\core.py proposals review external 5 reject --reason "Phone acceptance test only"
.\.venv\Scripts\python.exe .\core.py proposals review external 6 reject --reason "Duplicate-suppression acceptance test only"
.\.venv\Scripts\python.exe .\core.py proposals review model 1 reject --reason "Governed planner acceptance test only"
.\.venv\Scripts\python.exe .\core.py proposals review model 2 reject --reason "Governed planner refusal test only"
```

Then verify:

```powershell
.\.venv\Scripts\python.exe .\core.py proposals status
.\.venv\Scripts\python.exe .\core.py status-snapshot write
```

Expected result: `review_required` becomes zero while actions queued and actions
executed remain zero.
