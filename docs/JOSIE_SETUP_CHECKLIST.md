# JOSIE 0.99 / 1.0 — Running Setup State

Last reconciled: 2026-08-07

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
- [ ] OpenAI API connectivity blocked by zero API credit; ChatGPT subscription remains the Sophie control surface.
- [x] ChatGPT Remote paired for monitoring and steering from a phone.
- [x] Windows is configured not to sleep while on AC power; display timeout remains enabled.
- [x] Single-instance guard prevents duplicate Josie GUI processes.

## Immediate hardware and storage

- [x] Attach the 10 TB external USB HDD.
- [x] Read-only disk inventory completed on 2026-08-07: the 10 TB drive was not attached or detected; only the healthy internal SQF 128 GB SATA SSD was visible.
- [ ] Confirm its health, filesystem, drive letter, and usable capacity.
- [ ] Create directories for models, datasets, downloads, generated files, archives, logs, and backups.
- [ ] Keep active programs and databases on the internal SSD where practical.
- [ ] Add the external drive to Josie's monitoring and backup policy.
- [x] Drive detected as healthy 9.1 TiB UnionSine USB 3.2, GPT/NTFS, mounted at `D:` and labeled `External HDD`.
- [x] Existing Dropbox, OneDrive, Google, Immich, WD Backup, and other data preserved.
- [x] Created isolated `D:\Josie-Storage` directories for models, datasets, downloads, generated files, archives, backups, archived logs, and staging.
- [x] Configured a second daily Josie database backup under the external storage root.

## Remote access and interface

- [x] ChatGPT Remote available for current Codex supervision.
- [ ] Evaluate and install Tailscale for general secure remote access without router port forwarding.
- [x] Verified 2026-08-07: Tailscale is not currently installed.
- [ ] Define which local services, if any, Tailscale may expose.
- [ ] Evaluate Open WebUI after storage and container prerequisites are ready.
- [ ] Make the approved Josie interface usable from phone and laptop.

## Core orchestration

- [ ] Verify storage headroom before installing container tooling.
- [x] Verified 2026-08-07: Docker, system Node.js/npm, and n8n are not installed.
- [x] Verified 2026-08-07: `wsl.exe` exists but Windows Subsystem for Linux is not installed/enabled.
- [ ] Evaluate Docker Desktop versus a lighter Windows/WSL container runtime.
- [ ] Install container tooling only after explicit approval.
- [x] Offline-ready Compose package staged for n8n, Open WebUI, and a locked browser worker.
- [x] All service ports bind to loopback only; no LAN or Tailscale exposure is enabled.
- [x] Container preflight rejects mutable/unverified images, privileged mode, and Docker socket mounts.
- [x] Deployment safety suite passes 21 tests on 2026-08-08.
- [ ] Install and configure n8n with persistent data outside disposable containers.
- [ ] Build Josie as the orchestrator rather than a single chatbot.
- [ ] Add narrowly allowlisted Python and JavaScript workers.
- [ ] Add structured error handling and bounded retries.
- [ ] Add a bounded code-repair loop with explicit attempt and resource limits.

## Computer-use capability

- [ ] Add Playwright browser workers in an isolated profile.
- [x] Staged browser-worker health endpoint; navigation and execution remain disabled pending capability review.
- [ ] Support permitted navigation, form entry, downloads, uploads, and extraction.
- [ ] Prefer APIs or dedicated connectors over browser automation when available.
- [ ] Do not bypass platform rules, access controls, CAPTCHAs, or anti-bot systems.

## AI and model routing

- [x] Provider adapters exist with secrets excluded from Git.
- [x] Cloud calls are disabled by default.
- [ ] Define a zero-spend Sophie workflow through ChatGPT/Codex Remote.
- [ ] Define when Gemini free-tier use is acceptable, with an explicit budget gate.
- [ ] Compare provider answers only when the user has approved the associated API use.
- [ ] Add local models after storage and hardware capacity permit.
- [ ] Reconfirm whether Claude should serve as an optional editor/checker.

## Persistent memory and continuity

- [x] Persistent SQLite storage for messages, memories, tasks, reminders, approvals, and audit events.
- [x] Local backup and integrity verification.
- [ ] Import and organize selected Sophie/Josie project history.
- [x] Stage a local origin interview process for Dustin, Sophie, and Bernie; cloud interviews remain approval-gated.
- [x] Record project rules, philosophy, and major decisions with source and confirmed/unverified/rejected provenance.
- [ ] Add explicit memory review, correction, deletion, export, and restore workflows.
- [x] Add secret-free local memory/task export and a non-overwriting restore drill.
- [ ] Add approval-gated correction and deletion workflows; current approval records execute nothing.

## Safety and permissions

- [x] Explicit tool allowlist.
- [x] Non-executing approval inbox and audit trail.
- [x] Cloud-spending lock controlled outside provider code.
- [x] Encode capability-specific permissions in a tested, fail-closed machine-readable policy.
- [x] Unknown capabilities default to forbidden; overlapping policy groups are rejected.
- [ ] Require human approval for sensitive external communication or file transfer.
- [ ] Prohibit human impersonation where disallowed.
- [ ] Prohibit debt, contracts, significant spending, or wallet transfers without authorization.
- [ ] Create spending and wallet limits that Josie cannot modify herself.
- [x] Add a tested non-overwriting restore drill and incident/recovery runbook with exact commands.
- [x] Add a machine-readable Josie 1.0 acceptance audit that separates failures from human gates.

## Economic-agent foundation

- [x] Create a local, non-transactional Josie Upgrade Fund ledger.
- [x] Separate actual revenue, expenses, API costs, electricity, and balance from estimated savings.
- [x] Prevent estimated savings from being counted as earned money; ledger records cannot move or spend money.
- [ ] Keep tax, contracting, identity verification, and regulated business actions human-controlled.
- [ ] Evaluate wallet capability only after strict non-self-modifiable limits exist.
- [ ] Build opportunity discovery within platform rules and applicable law.
- [ ] Evaluate approved marketplaces, bounties, document processing, and machine-native services.
- [ ] Estimate expected profit and risk before accepting work.
- [ ] Track actual profitability and ROI by job type.
- [ ] Allow reinvestment proposals subject to human approval.

## Self-improvement and hardware research

- [ ] Track compatible upgrade components and target prices.
- [ ] Record expected capability improvement and total upgrade cost.
- [ ] Potential first major GPU target: RTX 3060 12 GB, subject to chassis, PSU, slot-power, thermals, and compatibility review.

## GPU and chassis path — not required for Josie 1.0

- [ ] Evaluate moving the AIMB-205G2/i7/32 GB platform into a standard case.
- [ ] Inspect the potential Dell shop chassis before assuming compatibility.
- [ ] Replace the 200/300 W-class PSU with a quality 550–650 W ATX PSU before a discrete GPU.
- [ ] Select a GPU with appropriate external power and measured slot draw compatible with the board.
- [ ] Treat the hardware/GPU phase as Josie 1.5 if Josie 1.0 means the functioning orchestration system.

## Critical path

1. Attach and validate the 10 TB external drive.
2. Define and install secure general remote access (Tailscale) if still needed beyond ChatGPT Remote.
3. Choose and install an appropriately lightweight container runtime.
4. Install n8n with durable storage and backups.
5. Add an isolated, allowlisted browser worker.
6. Evaluate and deploy Open WebUI.
7. Expand persistent memory governance and recovery.
8. Define the zero-spend Sophie workflow and explicitly budgeted Bernie bridge.

## Change-control rule

Destructive, privileged, authentication, network-exposure, spending, wallet,
contractual, or externally communicative actions always require explicit human
approval. Planned checklist entries are not authorization to perform them.
