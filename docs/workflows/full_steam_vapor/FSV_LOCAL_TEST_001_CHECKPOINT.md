# FSV-LOCAL-TEST-001 — Token-Safe Pre-Live Checkpoint

Checkpoint status: `SAFE / READY FOR CONTROLLED PHONE TEST / AWAITING DUSTIN CONFIRMATION`

Observed: 2026-08-19 12:35 ET

Authority: Dustin’s FSV Summit Unification Directive 1.0

## Bottom line

The future-execution token-retention blocker is remediated. The token-handling intake and portal workflows now retain no success, error, manual, or progress execution payloads. A separate restricted audit workflow receives an explicit safe-field allowlist and retains sanitized n8n execution evidence plus append-only Data Table events.

The local invalid-link test passed through Tailscale Serve. Tailscale supplied `dustin.boggess@gmail.com` as the authenticated requester; the portal rejected the invalid token with HTTP 403; audit execution 15 and its stored event contain no raw token, token digest, HTML, request headers/body, cookies, authorization data, or query secret.

No production FSV webhook is registered, no Gmail message has been sent, no `FSV-LOCAL-TEST-001` approval row has been created, and nothing can publish to Google.

The next actions require Dustin’s action-time confirmation:

1. Irreversibly delete legacy manual execution 6, whose private payload predates the no-save control and contains an unsent raw token. Its associated dry-run row is not in an accepted pending status and cannot be approved by the portal.
2. Publish the tailnet-only review portal, registering its GET and POST webhook paths.
3. Run the intake once, creating `FSV-LOCAL-TEST-001` and sending one mock review email to `dustin.boggess@gmail.com`.
4. Dustin completes the separate confirmation page from the phone; Remote then verifies the review row, sanitized audit events, reuse rejection, and execution evidence.

## Canonical and recovery paths

- Directive: `C:\Josie\docs\decisions\FSV_SUMMIT_UNIFICATION_DIRECTIVE_v1.0.md`
- This checkpoint: `C:\Josie\docs\workflows\full_steam_vapor\FSV_LOCAL_TEST_001_CHECKPOINT.md`
- Intake source: `C:\Josie\docs\workflows\full_steam_vapor\fsv-review-intake.json`
- Portal source: `C:\Josie\docs\workflows\full_steam_vapor\fsv-review-decision-portal.json`
- Audit append source: `C:\Josie\docs\workflows\full_steam_vapor\fsv-approval-audit-append.json`
- Audit schema initializer: `C:\Josie\docs\workflows\full_steam_vapor\fsv-approval-audit-table-initialize.json`
- Verified database recovery checkpoint: `D:\Josie-Storage\backups\full-steam-vapor\FSV-LOCAL-TEST-001\20260819-pre-live`
- Token-safe workflow checkpoint: `D:\Josie-Storage\backups\full-steam-vapor\FSV-LOCAL-TEST-001\20260819-token-safe-pre-live`

The token-safe checkpoint contains canonical sources, live n8n exports, SHA-256 values, and a manifest. It deliberately does not make a second full database copy while legacy execution 6 still contains the old token; the earlier verified online SQLite checkpoint remains the database-level recovery point.

## Services and routing

- n8n 2.30.5: `josie-n8n-1`, healthy, detached, `restart: unless-stopped`, loopback `127.0.0.1:5678`
- Open WebUI, browser worker, and proposal server: healthy, detached, restart-enabled
- Tailscale service: healthy
- n8n Serve route: `https://refurb.tail0ab4d2.ts.net:5678/` to loopback, tailnet only
- Public Funnel: disabled
- Phone peer: Dustin’s S26 Ultra, online, owned by the same Tailscale identity as Dustin

The production FSV webhook registry remains empty.

## n8n workflows

Project: `qJSF4KKZoSH4DntI`

### FSV - Google Post Review Intake

- ID: `bc26900f-a652-4581-a9a6-350b6ebcd202`
- Nodes: 24
- Published: no
- Test draft ID: `FSV-LOCAL-TEST-001`
- Adds duplicate-ID lookup before token generation
- Generates a 64-byte random token, stores only its HMAC digest, and sets a 72-hour expiry
- Appends sanitized draft, email-attempt, email-success, and email-failure events
- Gmail failure is audited before a generic fail-closed stop
- Execution data settings: success `none`, error `none`, manual `false`, progress `false`
- No Facebook, Gemini, OpenAI, Google Business Profile, or publishing node

### FSV - Review Decision Portal

- ID: `de619731-b931-4c7e-9296-3cc51e1702de`
- Nodes: 25
- Published: no
- GET: `/webhook/fsv-google-review`
- POST: `/webhook/fsv-google-review-decision`
- GET records intent and renders a separate confirmation page; it never changes state
- POST rechecks HMAC, expiry, allowlisted action, pending state, and Dustin’s Tailscale identity
- Single use is enforced by a conditional update matching review ID, token digest, and original pending state
- APPROVE and EDIT end in `*_not_published`; SKIP ends in `skipped`
- Invalid, expired, reused, and concurrent duplicate submissions produce sanitized audit events
- Execution data settings: success `none`, error `none`, manual `false`, progress `false`
- No publishing node

### FSV - Approval Audit Append

- ID: `a4c78e6d-8c18-4b93-8e3e-2ae60e5af501`
- Nodes: 5
- Published: yes
- No webhook or external connector
- Caller allowlist contains only the intake, portal, and schema-initializer workflow IDs
- Rejects unknown fields and credential-like names or values
- Data Table operation is insert-only
- Retains sanitized execution history as evidence

### FSV - Initialize Approval Audit Table

- ID: `a4c78e6d-8c18-4b93-8e3e-2ae60e5af502`
- Nodes: 5
- Inactive/manual
- Creates the audit table only if absent and appends a sanitized schema-initialization event

## Persistent storage

### Review records

- Table: `FSV Google Post Reviews`
- ID: `7is92GD4xCYEKid9`
- Current rows remain `FSV TEST-001` and `FSV TEST-002`; `FSV-LOCAL-TEST-001` does not exist yet

### Append-only audit events

- Table: `FSV Approval Audit Events`
- ID: `gJJLqRCsgz6LW8Oo`
- Project: `qJSF4KKZoSH4DntI`
- Physical table: `data_table_user_gJJLqRCsgz6LW8Oo`
- 27 user fields plus n8n row metadata
- Runtime workflow uses insert only

Current sanitized events:

- `FSV-AUDIT-13-0`: `AUDIT_TABLE_INITIALIZED`, success, no token issued
- `FSV-AUDIT-15-0`: `LINK_INVALID`, APPROVE intent, approver `dustin.boggess@gmail.com`, basis `TAILSCALE_IDENTITY_HEADER`, token state `invalid`, HTTP 403, result `REJECTED`

## Verification evidence

- All four workflow JSON files parse
- All 24 Code nodes parse as JavaScript
- Every workflow connection target exists
- Live exports confirm node counts and execution-retention settings
- Audit schema initializer execution 12: success
- Sanitized audit subworkflow execution 13: success
- Tailscale invalid-link parent execution 14: immediately hidden/marked deleted by the no-save policy
- Sanitized audit execution 15: success and retained
- Audit execution 15 payload scan: no forbidden key and no query secret
- Stored audit event 15 confirms Dustin’s Tailscale identity header
- Offline portal tests passed: separate GET confirmation, expiry rejection, GET reuse rejection, invalid-token rejection, valid APPROVE preparation, POST expiry rejection, and POST reuse rejection
- Audit validator tests passed: safe event accepted; unknown token field, query credential pattern, and unknown event rejected
- Production webhook registry count: zero
- No Google publishing connector present

## Remaining uncertainty and controls

- Gmail send-only OAuth is configured but the actual send has not been tested.
- A real valid token, phone confirmation, conditional update, and reuse attempt remain for the controlled live loop.
- n8n necessarily writes an initial in-flight webhook execution bundle before workflow code runs. With the no-save settings, production token-bearing runs are absent from normal history immediately and are hard-deleted by pruning, generally within 15 minutes. No full database backup should be taken during that interval.
- Legacy execution 6 remains until Dustin authorizes its irreversible deletion. Its row status is `dry_run`, so the portal does not accept it as pending.
- The n8n cookie setting remains compatible with local loopback administration; external access is HTTPS through Tailscale and the service does not listen on the LAN.

## Recovery

- No service was stopped.
- No workflow, credential, review row, or execution was deleted.
- The review portal and intake remain unpublished.
- The earlier verified online SQLite checkpoint is the database rollback point.
- The token-safe workflow checkpoint provides both canonical source and live export versions.
- Before the phone test, rollback is simply to leave the two external workflows unpublished.

## Superseding controlled-recovery checkpoint — 2026-08-19 14:47 ET

This section supersedes earlier status statements above where they differ.

- `Build Review Email` was repaired by removing only the two stray numeric fragments identified in the failed live node. The resulting JavaScript parses successfully.
- The original failed execution had already discarded its retained node data, so Dustin explicitly authorized one controlled token reissue on the existing `FSV-LOCAL-TEST-001` row.
- A verified online SQLite backup was created before the reissue at `D:\Josie-Storage\backups\full-steam-vapor\FSV-LOCAL-TEST-001\20260819-authorized-reissue-pre-execution\n8n-database.sqlite`.
- Backup integrity: `ok`; SHA-256: `F86031C424E79DEA5ABB995B124E37236C881D99F89805CCBA240878EA2C8ABD`.
- The existing row was preserved. Only its stored token HMAC and expiry were changed; review content, review ID, `review_pending` status, and `not_published` result were preserved.
- The established 72-hour expiry was used. The new expiry is `2026-08-22T18:47:14.214Z`.
- One sanitized `TOKEN_REISSUED` event was appended.
- One `EMAIL_SEND_ATTEMPTED` event was appended.
- Gmail returned the controlled failure path. One `EMAIL_SEND_FAILED` event was appended; no success event exists.
- Gmail All Mail contains zero messages with subject `[FSV-LOCAL-TEST-001] Google Business draft ready for review`. No resend was attempted.
- The recovery execution started and finished `Send Review Email` exactly once. Automatic retry was disabled.
- Sensitive execution scanning found no retained raw approval token, token-hash field, signed review URL, or email HTML.
- Recovery workflow `a4c78e6d-8c18-4b93-8e3e-2ae60e5af503` is retained as evidence but is inactive and unpublished.
- Audit workflow `a4c78e6d-8c18-4b93-8e3e-2ae60e5af501` remains active and now allowlists the sanitized `TOKEN_REISSUED` event plus the exact recovery workflow caller.
- Decision Portal remains active and Tailscale-only. Intake remains inactive/manual.
- Google publishing remains disconnected. The row has no Google post ID and remains `not_published`.

Canonical workflow exports:

- `C:\Josie\docs\workflows\full_steam_vapor\fsv-approval-audit-append.json`
- `C:\Josie\docs\workflows\full_steam_vapor\fsv-controlled-token-reissue-recovery.json`
- Prior audit export preserved at `C:\Josie\docs\workflows\full_steam_vapor\fsv-approval-audit-append.pre-token-reissue-20260819.json`

Current blocker: the n8n Gmail send returned only the sanitized generic failure result and no HTTP status. Because the newly issued raw token was deliberately not retained and the email was not delivered, another send would require a newly authorized token reissue after diagnosing the Gmail credential/runtime path. No such second reissue or send is authorized by this checkpoint.
