# FSV Summit Unification Directive — Version 1.0

Status: `CANONICAL / DUSTIN-DIRECTED`

Recorded: 2026-08-19

Scope: All Full Steam Vapor work performed through Remote and Josie.

Continuity rule: Preserve this directive locally and do not rely on a chat transcript alone.

## Current identities and authority

1. Dustin is the owner, Summit chair, final business decision-maker, and required approver for consequential or external actions.
2. Sophie is Dustin’s conversational strategy and synthesis partner. Sophie works through ambiguity, compares options, preserves business context, and produces bounded execution briefs.
3. Bernie/Gemini is a mandatory Full Steam Vapor co-planner. Bernie contributes direct Google-side knowledge, Google Business Profile information, current verification, long-context and multimodal analysis, and tactical recommendations. Do not treat Bernie as an optional reviewer or subordinate voice.
4. Remote is the execution role operating against Josie’s real desktop, files, applications, browser sessions, Docker services, n8n workflows, PowerShell, and other approved local tools. Remote executes approved briefs and returns evidence. Remote must not silently expand business scope or substitute its own strategy for a Summit decision.
5. Josie is currently the physical workstation, storehouse, gateway, and automation mediator. Josie is not yet an independent decision-making persona. Future promotion to an air-traffic-controller role will be handled separately after appropriate hardware, model, permission, reliability, and recovery gates are met.
6. n8n is a deterministic facilitator. It may store, synchronize, route, notify, validate, retry, and log. It may not make final business or publishing decisions.

## Authoritative Full Steam Vapor facts

- Huntington is closed and must never be represented as active.
- The active location is Teays Valley/Hurricane, West Virginia.
- Hours are Monday–Friday 8:00 AM–8:00 PM; Saturday 11:00 AM–8:00 PM; Sunday closed.
- Full Steam Vapor has served the local community since 2014.
- The business emphasizes knowledgeable, friendly, one-on-one service for adult customers.
- Facebook posts are locally vetted source material.
- Google compatibility review should remain narrow and platform-specific.
- Nothing publishes automatically.
- Approval email address is `dustin.boggess@gmail.com`.
- Google draft approval must provide Approve, Edit, and Skip.
- Approve must open a separate confirmation page.
- Approval tokens must be signed, single-use, and expiring.
- Log approver, approval time, source, draft, Google post ID when applicable, and final result.

## Preserve current work

Do not erase, replace, restart, or duplicate the current FSV approval MVP. First complete or safely checkpoint `FSV-LOCAL-TEST-001`. Record its exact status, paths, containers, n8n workflows, database objects, URLs, credentials configured, tests passed, and remaining blockers.

After the current MVP reaches a safe checkpoint, build the FSV Summit foundation.

## FSV Summit foundation

Create or preserve one canonical Full Steam Vapor project root. Do not create competing project folders if one already exists. Report its exact path.

Inside the canonical project, establish:

- `FSV_SUMMIT_CHARTER.md`
- `FSV_CURRENT_STATE.md`
- `FSV_CAPABILITIES.json` or an equivalent structured capability registry
- A schema or migration directory
- A persistent Summit database separate from n8n’s internal application database
- Export and backup locations
- Documentation identifying the canonical Google Sheet and n8n workflows

Use a separate SQLite database in WAL mode unless the existing audited stack provides a clearly superior persistent database. n8n should be the sole database writer to avoid concurrency conflicts.

Create a private Google Sheet named `FSV Summit` as the shared collaboration surface. Preferred logical sections or tabs are:

- Threads
- Messages
- Decisions
- Tasks
- Capabilities
- Artifacts
- Audit

Required message-level fields include:

- `thread_id`
- `message_id`
- `parent_id`
- `author`
- `recipient` or `audience`
- `message_type`
- `content`
- `source_references`
- `created_at`
- `version`
- `status`
- `ingestion_result`

Required task fields include:

- `task_id`
- `originating_decision`
- `approved_scope`
- `explicit_exclusions`
- `executor`
- `approval_requirements`
- `status`
- `start_timestamp`
- `completion_timestamp`
- `affected_systems`
- `verification_evidence`
- `rollback_or_recovery_information`
- `blockers`

Use append-only contributions. Sophie and Bernie must not overwrite each other’s entries. Corrections create a new version linked to the earlier message.

## Capability registry

Record capabilities as observed facts rather than assumptions. For each participant, record:

- What it can read
- What it can write
- What it can execute
- Authentication surface
- Whether access is supervised, browser-driven, connector-based, API-based, or local
- Whether it can operate unattended
- Confirmation requirements
- Known limitations
- Last verification time

Explicitly verify and record:

- Sophie’s Google Drive/Sheet read and write route
- Bernie’s Google Business Profile access
- Bernie’s Google Drive/Sheet read and write route
- Remote’s local files, Chrome, POS, Docker, n8n, and PowerShell access
- Josie’s Tailscale and persistent-service health
- Gmail send and, if required, approval-response processing

Do not infer that access to a visible webpage equals API access.

## Summit state machine

Implement these states:

- `INTAKE`
- `CONTEXT_READY`
- `WAITING_FOR_SOPHIE`
- `WAITING_FOR_BERNIE`
- `READY_FOR_SYNTHESIS`
- `WAITING_FOR_DUSTIN`
- `APPROVED_FOR_REMOTE`
- `EXECUTING`
- `VERIFYING`
- `COMPLETE`
- `BLOCKED`
- `SKIPPED`

Either Sophie or Bernie may originate a thread.

For Full Steam Vapor work, a thread cannot become `APPROVED_FOR_REMOTE` until:

- Sophie has contributed or explicitly deferred;
- Bernie has contributed or explicitly recorded that no additional input is needed;
- the positions have been synthesized;
- Dustin has approved the decision.

Only Dustin can waive the normal quorum for an emergency or clearly mechanical task.

## Routing and turn control

Use n8n to:

- Poll or watch the shared surface;
- Validate new entries;
- Assign stable IDs;
- Write canonical records into SQLite;
- Prevent duplicate ingestion;
- Track unread messages and expected next participant;
- Enforce a default maximum of two Sophie/Bernie discussion rounds;
- Notify Dustin when a decision is needed;
- Generate a bounded Remote task after approval;
- Record execution results and evidence;
- Update the readable current-state snapshot;
- Retry transient mechanical failures safely;
- Mark unresolved failures `BLOCKED` rather than guessing.

Do not create autonomous model-to-model loops without a round limit, cost limit, timeout, and human stop condition.

## Communication format

Each substantive Sophie or Bernie contribution distinguishes:

- Confirmed facts
- Sources or accessed systems
- Analysis or inference
- Recommendation
- Best-positioned executor
- Risks or Google compatibility concerns
- Unanswered questions
- Requested next participant

Remote task packets include:

- Mission
- Authoritative context
- Approved scope
- Explicit exclusions
- Inputs and source locations
- Required outputs
- Security and approval gates
- Verification tests
- Evidence required
- Rollback or recovery expectation
- Completion-report format

## Security and external actions

- Never place passwords, tokens, cookies, API secrets, or approval signing keys in Google Sheets, Markdown, chat messages, or execution reports.
- Keep services detached and backgrounded; do not leave CMD or PowerShell windows stealing foreground focus.
- Limit administrative interfaces and approval pages to Tailscale unless a separately reviewed public endpoint is required.
- Use signed, expiring, single-use approval links.
- A first click may express intent but must not publish.
- Publishing requires the separate confirmation action.
- Log every approval, denial, edit, skip, expiration, attempted token reuse, API response, and publishing result.
- Preserve recoverability and make backups before material schema or configuration changes.

## Implementation phases

### Phase 0

Finish and verify the current local approval MVP. Do not add Facebook, Gemini, OpenAI, POS, or Google publishing to that MVP.

### Phase 1

Create the Summit charter, persistent ledger, capability registry, Google Sheet surface, SQLite store, synchronization, and readable state snapshot.

### Phase 2

Verify Sophie and Bernie can independently read and append to the Summit without manual copying of the full thread.

### Phase 3

Conduct `SUMMIT-TEST-001` using a harmless read-only Full Steam Vapor question. Require one Sophie contribution, one Bernie contribution, one synthesis, one Dustin decision, one Remote task, and one verified completion report.

### Phase 4

Add read-only sources in controlled order: Google Business listing, POS through Chrome, Facebook source ingestion, and relevant Drive material.

### Phase 5

Add draft generation, email review, signed approval, and confirmed Google publishing. Publishing remains the final integration.

Do not connect every service at once. Each phase must pass before promotion.

## Required checkpoint report

Before implementing Phase 1, return:

- Current `FSV-LOCAL-TEST-001` status
- Existing canonical project path
- Running container and service inventory
- Existing n8n workflow inventory
- Current Tailscale routing
- Current persistent-storage locations
- Proposed Summit file paths and database
- Proposed Google Sheet structure
- Needed OAuth or user permission prompts
- Conflicts with existing work
- Safe implementation sequence

After each phase, return:

- What changed
- Exact files and workflows created or modified
- Services affected
- Tests executed
- Evidence and results
- Security controls verified
- Failures or unresolved uncertainty
- Rollback information
- Recommended next phase

Do not claim unification is complete until `SUMMIT-TEST-001` passes end to end with real contributions and a real Remote completion record.
