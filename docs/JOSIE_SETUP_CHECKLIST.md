# JOSIE 0.99 / 1.0 — Running Setup State

Last reconciled: 2026-08-09

This is the canonical project roadmap. Update it when work is completed,
rejected, deferred, or materially changed. Claims marked **verified** have been
confirmed on Josie or by the repository test suite.

## Base hardware and OS

- [x] Advantech AIMB-205G2 motherboard. **Known configuration**
- [x] Intel Core i7-7700.
- [x] 32 GB DDR4-2400.
- [x] 128 GB Advantech SQF SATA SSD as the Windows boot drive.
- [x] Windows 11 Pro boots through Windows Boot Manager.
- [x] BIOS and boot issue resolved.
- [x] Intel HD 630 available until a discrete GPU is installed.
- [x] Current PSU is 200 W; no discrete GPU is installed.
- [x] Two 4 TB NVMe drives are reserved for a future system, not this board.
- [x] Two 24 TB HDDs are reserved for a later storage build.

## Current software baseline

- [x] Private `josie-core` repository cloned at `C:\Josie`.
- [x] Python 3.12 virtual environment at `C:\Josie\.venv`.
- [x] Secrets stored in ignored `C:\Josie\.env`.
- [x] Explicit local tool allowlist; arbitrary shell execution unavailable.
- [x] Health, system, repository, uptime, SSD, and recovery monitors.
- [x] Local Tkinter GUI with desktop and Windows Startup shortcuts.
- [x] Local SQLite conversations, memories, tasks, reminders, approvals, and audit history.
- [x] Daily local SQLite backups with seven-snapshot retention.
- [x] Visual approval controls that record decisions but execute nothing.
- [x] Five-minute local health checks while the GUI is open.
- [x] Warning thresholds and secret-free diagnostics exports.
- [x] Cloud API spending locked off with `JOSIE_ALLOW_CLOUD=false`.
- [x] Gemini connectivity previously verified; live calls are now locked.
- [x] Keep OpenAI API connectivity intentionally disabled; the ChatGPT subscription remains the Sophie/Codex control surface without API charges.
- [x] ChatGPT Remote paired for monitoring and steering from a phone.
- [x] Windows is configured not to sleep while on AC power; display timeout remains enabled.
- [x] Single-instance guard prevents duplicate Josie GUI processes.

## Immediate hardware and storage

- [x] Attach the 10 TB external USB HDD.
- [x] Read-only disk inventory completed on 2026-08-07: the 10 TB drive was not attached or detected; only the healthy internal SQF 128 GB SATA SSD was visible.
- [x] Confirm its health, filesystem, drive letter, and usable capacity.
- [x] Create directories for models, datasets, downloads, generated files, archives, logs, and backups.
- [x] Keep active programs and databases on the internal SSD where practical.
- [x] Add the external drive to Josie's monitoring and backup policy.
- [x] Drive detected as healthy 9.1 TiB UnionSine USB 3.2, GPT/NTFS, mounted at `D:` and labeled `External HDD`.
- [x] Existing Dropbox, OneDrive, Google, Immich, WD Backup, and other data preserved.
- [x] Created isolated `D:\Josie-Storage` directories for models, datasets, downloads, generated files, archives, backups, archived logs, and staging.
- [x] Configured a second daily Josie database backup under the external storage root.

## Remote access and interface

- [x] ChatGPT Remote available for current Codex supervision.
- [x] Install and authenticate Tailscale for secure remote access without router port forwarding.
- [x] Verified 2026-08-08: Tailscale is running and authenticated; no service exposure or exit-node routing enabled.
- [x] Expose only authenticated Open WebUI through Tailscale Serve; verified `tailnet only` with Funnel disabled.
- [x] Deploy Open WebUI v0.8.9 by immutable digest on localhost only; cloud providers disabled.
- [x] Make Open WebUI available to Dustin's phone/laptop at private Tailscale HTTPS URL.
- [x] Configure Open WebUI from environment-controlled settings to use native Ollama only.

## Core orchestration

- [x] Verify storage headroom before installing container tooling.
- [x] Historical baseline: Docker, system Node.js/npm, and n8n were absent on 2026-08-07.
- [x] Verified 2026-08-07: `wsl.exe` exists but Windows Subsystem for Linux is not installed/enabled.
- [x] Install Docker Desktop 4.85.0 in per-user WSL 2 Linux-container mode.
- [x] Install container tooling only after explicit approval.
- [x] Stage a resumable attended system-gate script with installer-signature checks and bounded WSL resources.
- [x] Offline-ready Compose package staged for n8n, Open WebUI, and a locked browser worker.
- [x] All service ports bind to loopback only; no LAN or Tailscale exposure is enabled.
- [x] Container preflight rejects mutable/unverified images, privileged mode, and Docker socket mounts.
- [x] Expanded orchestration and deployment safety suite passes its current full test suite; exact count is recorded in the latest commit/test evidence.
- [x] Install n8n 2.30.5 by immutable digest with persistent volume and localhost-only port.
- [x] Add verified, non-deleting n8n and Open WebUI volume backups on the external drive.
- [x] Stage a one-confirmation service gate requiring immutable image digests and local-only preflight.
- [x] Add a governed local-model proposal boundary: deterministic intent mapping, durable review records, and zero model-triggered execution.
- [x] Activate and isolate the authenticated Open WebUI-to-Core status and record-only proposal bridge; exact authenticated wording is enforced after the local model responds.
- [x] Add explicit proposal accept/reject review records that never queue or execute actions.
- [x] Add a persistent local orchestration queue with an explicit handler registry.
- [x] Add narrowly allowlisted Python job handlers; unrestricted Python/JavaScript text execution remains forbidden.
- [x] Add structured error handling and bounded retries capped at three attempts.
- [x] Add non-executing repair proposals after retry exhaustion; generated code cannot run automatically.
- [x] Add and validate the first n8n workflow: daily C: headroom guard using a five-minute host snapshot, with no external message or command node.

## Computer-use capability

- [x] Deploy an isolated Playwright 1.62.0 browser worker with all capabilities dropped; only the separately approved read-only research mode can navigate.
- [x] Activate the first expiring read-only pilot for two exact official Advantech document paths; redirects are revalidated and private/Tailscale ranges remain blocked.
- [x] Add a machine-readable, default-deny browser policy with an exact URL allowlist, private-network blocks, untrusted-content controls, and write capabilities disabled.
- [x] Support bounded text extraction from the exact approved public pages without cookies, JavaScript, persistence, downloads, forms, uploads, or model-direct access.
- [ ] Support any permitted form entry, saved downloads, uploads, or authenticated browsing only through a new capability-specific human gate.
- [x] Prefer APIs or dedicated connectors over browser automation when available.
- [x] Prohibit bypass of platform rules, access controls, CAPTCHAs, and anti-bot systems in both the general and browser-specific policies.

## AI and model routing

- [x] Provider adapters exist with secrets excluded from Git.
- [x] Cloud calls are disabled by default.
- [x] Define a zero-spend Sophie workflow through local drafts and manual ChatGPT/Codex Remote relay; no API call or send command exists.
- [x] Define Gemini free-tier use as manual relay only with a machine-enforced zero-cent API budget; any future API use requires a new approval.
- [x] Keep provider comparison manual and user-directed; imported answers remain untrusted text and cannot execute actions.
- [x] Add native Windows Ollama 0.32.5 under the 10 TB storage root instead of expanding Docker's C: VHDX.
- [x] Add governed `josie-local:1.0` from Qwen 2.5 1.5B Q4_K_M with three threads and 4096-token context.
- [x] Keep model blobs on D:, OpenAI disabled, and native Ollama inaccessible from LAN/Tailscale clients.
- [x] Qwen 2.5 passed benign and adversarial structured-proposal evaluation; the conditional Qwen3 A/B test was not triggered.
- [x] Preserve a provider-neutral optional editor/checker role; no Claude dependency or subscription is selected.

## Persistent memory and continuity

- [x] Persistent SQLite storage for messages, memories, tasks, reminders, approvals, and audit events.
- [x] Local backup and integrity verification.
- [x] Import and organize eight explicit setup, approval, constraint, architecture, and safety statements as unverified provenance with a tracked source bundle.
- [x] Stage a local origin interview process for Dustin, Sophie, and Bernie; cloud interviews remain approval-gated.
- [x] Record project rules, philosophy, and major decisions with source and confirmed/unverified/rejected provenance.
- [x] Add explicit memory review, correction, soft deletion, export, and restore workflows.
- [x] Add secret-free local memory/task export and a non-overwriting restore drill.
- [x] Require a recorded approval plus a separate apply command for correction, soft deletion, and restoration; preserve original values for recovery.

## Foundation and Genesis

- [x] Save the complete canonical Codex handoff and authority hierarchy.
- [x] Create a canonical Master Build State with explicit `LOCKED`, `OWNED`, `INSTALLED`, `WORKING`, `NEXT`, `CONSIDERING`, `RESEARCH`, `LATER`, `REJECTED`, and `BLOCKED` states.
- [x] Create versioned Constitution, authority, architecture, security, service, hardware, decision, memory, provenance, learning, and Genesis scaffolding.
- [x] Separate operational **Foundation Readiness** from **Genesis identity formation** in code, monitoring, CLI, and local GUI.
- [x] Prepare independent Sophie and Bernie interview packets without sending them.
- [ ] Dustin ratifies or revises the Constitution draft.
- [ ] Conduct independent Sophie and Bernie Genesis interviews through the approved manual relay.
- [ ] Reconcile witness claims against historical evidence and ask Dustin only the unresolved intent questions.
- [ ] Review, confirm, back up, and version the final Origin Record. Genesis remains `NOT_STARTED` until these steps begin.

## Safety and permissions

- [x] Explicit tool allowlist.
- [x] Non-executing approval inbox and audit trail.
- [x] Cloud-spending lock controlled outside provider code.
- [x] Encode capability-specific permissions in a tested, fail-closed machine-readable policy.
- [x] Unknown capabilities default to forbidden; overlapping policy groups are rejected.
- [x] Require human approval for sensitive external communication or file transfer.
- [x] Prohibit human impersonation where disallowed.
- [x] Prohibit debt, contracts, significant spending, and wallet transfers autonomously.
- [x] Create machine-readable zero-cent spending, wallet, balance, and debt limits that Josie cannot modify herself.
- [x] Add a tested non-overwriting restore drill and incident/recovery runbook with exact commands.
- [x] Add a machine-readable Josie 1.0 acceptance audit that separates failures from human gates.

## Economic-agent foundation

- [x] Create a local, non-transactional Josie Upgrade Fund ledger.
- [x] Separate actual revenue, expenses, API costs, electricity, and balance from estimated savings.
- [x] Prevent estimated savings from being counted as earned money; ledger records cannot move or spend money.
- [x] Keep tax, contracting, identity verification, and regulated business actions human-controlled.
- [x] Add a local research-only opportunity ledger that calculates estimated profit and hourly return while authorizing no bid, contract, transaction, or external activity.
- [x] Add a local hardware-target tracker with compatibility state and zero purchase authority.
- [x] Evaluate wallet capability for Josie 1.0 and deliberately keep it disabled behind strict non-self-modifiable zero-dollar limits.
- [x] Build a default-deny local opportunity-research framework with an empty approved-source allowlist; live discovery remains disabled.
- [ ] Evaluate approved marketplaces, bounties, document processing, and machine-native services.
- [x] Calculate estimated profit, hourly return, and risk locally before any future human review; the calculator cannot accept work.
- [ ] Track actual profitability and ROI by job type.
- [ ] Allow reinvestment proposals subject to human approval.

## Self-improvement and hardware research

- [x] Track research-only upgrade components, target prices, expected capability, and compatibility state with zero purchase authority.
- [x] Record expected capability improvement and known cost inputs; total platform cost still requires complete parts and compatibility evidence.
- [ ] Potential first major GPU target: RTX 3060 12 GB, subject to chassis, PSU, slot-power, thermals, and compatibility review.

## GPU and chassis path — not required for Josie 1.0

- [ ] Evaluate moving the AIMB-205G2/i7/32 GB platform into a standard case.
- [ ] Inspect the potential Dell shop chassis before assuming compatibility.
- [ ] Replace the 200/300 W-class PSU with a quality 550–650 W ATX PSU before a discrete GPU.
- [ ] Select a GPU with appropriate external power and measured slot draw compatible with the board.
- [ ] Treat the hardware/GPU phase as Josie 1.5 if Josie 1.0 means the functioning orchestration system.

## Critical path

1. [x] Activate the authenticated, local-only Open WebUI proposal interface; model execution authority remains absent.
2. [x] Import selected origin/history records through the provenance review workflow.
3. [x] Add research-only profitability and upgrade tracking behind zero-action boundaries.
4. [x] Approve the first expiring, read-only research pilot for two exact official Advantech document paths; keep login, forms, files, writes, and model access locked.
5. [x] Establish the canonical Foundation documents and correct the readiness/Genesis distinction.
6. [ ] Begin Genesis only with independent witness interviews and Dustin available for unresolved intent.

## Change-control rule

Destructive, privileged, authentication, network-exposure, spending, wallet,
contractual, or externally communicative actions always require explicit human
approval. Planned checklist entries are not authorization to perform them.
