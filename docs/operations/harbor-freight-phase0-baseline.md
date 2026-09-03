# Harbor Freight Phase 0A baseline

Observed 2026-09-03 from `C:\Josie`. This is an existence/source inspection, not a restore certification. Database, credential, receipt, lock, and log contents were not accessed.

## Git and project state

- Starting branch: `maintenance/delegate-local-gpu-audit-20260901`.
- Starting commit: `fd833f58e85b50945d0507ac610c3043eaf97159`.
- Phase 0A work branch: `maintenance/delegate-harbor-freight-phase0a-20260903`.
- Pre-existing modified files: `.gitignore`, `BACKUP_CHECKLIST.md`, `CURRENT_STATE.md`, `GPU_UPGRADE_PLAN.md`, `core.py`, `deploy/.env.services.example`, `deploy/compose.yaml`, three `deploy/open-webui` Python files, four state/research/setup/decision documents, four `josie` modules, `scripts/Start-JosieOllama.ps1`, and two tests.
- Pre-existing untracked work includes `PRE_GPU_QWEN3_BASELINE.md`, Summit relay browser-extension artifacts (including a sensitive `.pem`, not opened), continuity/identity/local-code/Summit config, new core/context/continuity/Summit modules and tests, operational/architecture documents, relay requirements and management scripts, an Ollama-startup backup folder, a SQLite tools ZIP, and `nul`. These remain unrelated and preserved.
- Top-level structure observed (excluding policy-excluded `.git`, `data`, `logs`, and `startup-backup` inspection): `.venv`, `browser-extension`, `config`, `core`, `deploy`, `docs`, `josie`, `scripts`, and `tests`, plus root documentation, launchers, requirements, baselines, and source entry points.

## Test baseline

- Documented command: `.venv\Scripts\python.exe -m unittest discover -s tests -v` (`README.md` and `RUNBOOK.md`).
- Pre-change result: exit 1; 208 tests ran in 76.594 seconds; 206 passed and 2 failed.
- Failures: `test_native_model_firewall_is_docker_scoped` expected `172.31.0.0/20` in the already-modified `scripts/Set-JosieOllamaFirewall.ps1`; `test_direct_browser_config_uses_installed_chrome_and_no_extension` expected `config["headless"]` true in pre-existing Summit work.
- A preliminary `python -m pytest` exited 1 because system Python has no pytest module. Nothing was installed. It is not the repository's documented suite.
- Post-change result using the same documented command: exit 1; 211 tests ran in 75.188 seconds; 209 passed and the same 2 pre-existing tests failed. All 3 added backup-verifier tests passed, so Phase 0A introduced no additional test failure.

## Durable state and state owners

Repository sources identify, without opening the state itself:

- `data/josie.db`: primary SQLite state for memory, history/evidence, tasks, consultant/maintenance/audit records and related registries. `josie/storage.py` is the central schema/state implementation.
- `data/backups`: local daily/checkpoint SQLite backups; the implementation uses SQLite's backup API and retains seven daily generations.
- `data/private`: private service tokens/source configuration, job/runtime state, and worker receipts. Contents were not inspected.
- Docker named volumes `josie_open_webui_data` and `josie_n8n_data`: Open WebUI conversations/function records and n8n workflow/execution/encryption state.
- `D:\Josie-Storage`: documented live apps/models plus evidence, proposals, status, secrets, and backup generations. It was not inspected in this task.
- `config`, `deploy`, `docs/identity`, `docs/constitution`, and repository history: policy, deployment definitions, identity/genesis, governance, and code/config provenance.
- `.env` and `deploy/.env.services`: required secret/image configuration; presence/name only was observed and contents were not read.

Likely state owners are Josie Core/SQLite, Open WebUI's named volume, n8n's named volume, private worker receipt directories, and the external storage hierarchy. Git owns versioned source and documentation but is explicitly not a data backup.

## Backup and restore inventory

- `core.py backups create-local` and `core.py backups create-checkpoint --label ...` use SQLite-consistent backup machinery.
- `core.py tools run restore-drill --json` restores the newest backup into memory and does not overwrite the live database.
- The storage monitor is documented as a 300-second loop that creates daily local/external snapshots.
- `scripts/Backup-JosieServices.ps1` is a disruptive, approval-window helper: it stops n8n/Open WebUI, archives their volumes read-only to `D:\Josie-Storage\backups\services`, writes hashes/model inventory, and restarts services. It was inspected but not run.
- `BACKUP_CHECKLIST.md` records two 2026-08-28 SQLite backups as integrity-checked and older 2026-08-26 service archives; it explicitly says current full-service parity, off-device coverage, and a current full-system image were not established.
- `docs/INCIDENT_AND_RECOVERY.md`, `RUNBOOK.md`, and the backup checklist provide recovery gates. A real restore requires Dustin approval and must not overwrite live state during validation.
- Added in Phase 0A: `python -m josie.backup_verify` is existence-only, default-dry-run, copies nothing, reads no contents, reports external dependencies as unverified, and exits nonzero for missing required repository-local inputs.

## Services and tools

- Repository definitions document native Josie conversation control/Core, native Ollama, Docker Desktop/WSL2, Open WebUI, n8n, browser worker, proposal server, storage monitor, Tailscale, and optional Codex/Gemini/OpenCode workers.
- A safe Windows service query observed `Tailscale` in `Running` state. It found no named Docker or Ollama Windows service.
- Live process inventory was not available: `Get-CimInstance Win32_Process` was sandbox-denied with `Access denied`; no bypass was attempted.
- Container state was not queried because the documented Compose inventory requires the protected service environment file. Therefore intended Compose services must not be represented as live-verified.
- Documented always-running/stateful candidates are Tailscale, Docker Desktop/WSL2, Open WebUI, n8n, native Ollama, conversation control, and the storage monitor. Optional browser/proposal/Summit and CLI workers are not assumed always running.

## Coding, delegation, and receipts

- `Delegate Codex:` routes through the host conversation-control service to the existing ChatGPT-authenticated Codex CLI in this real repository; `consult_codex` remains advisory/read-only.
- Maintainer Mode is a separate fail-closed mechanism using configured read/write/command/Git gates and Dustin approval for protected actions.
- Local code/OpenCode and optional Gemini/Codex workers are documented; execution is explicit rather than inferred from ordinary chat.
- Delegation uses a single Git lock and append-only private receipt/event/final/error files; their contents and the lock were not accessed. Maintainer records are documented as stored in existing SQLite. Application logging is configured in `josie/logging_setup.py`; logs were not accessed.

## Restoration dependencies and unknowns

Required restoration inputs include consistent SQLite backups (including WAL-aware capture), matching Open WebUI/n8n volumes and image/schema versions, matching service encryption/authentication secrets, Git source/config, identity/governance records, D:-hosted runtimes/models/evidence, native Ollama state, Docker's C: VHDX under a consistent snapshot procedure, Tailscale account/Serve recovery, and Windows startup/task/firewall configuration.

Unknown or requiring later interactive Dustin access:

- Current integrity/freshness and isolated restorability of all SQLite and service backups.
- Current Open WebUI/n8n volume contents, container health, exact running images, and encryption-key coverage.
- Current D: assets, hashes, capacity, and whether any independent/off-device recovery copy exists.
- Live process ownership for Ollama, conversation control, storage monitoring, and optional workers.
- Tailscale Serve/account recovery details and Windows scheduled-task/startup/firewall export status.
- Whether the untracked Summit/browser artifacts and current dirty changes are intended, complete, and covered by recovery media.
- A Dustin-attended maintenance window is required for any fresh service backup, isolated restore drill involving protected state, secret escrow validation, or Windows/external-drive recovery verification.

No architecture, service, model, authentication, database, durable data, or production configuration was changed by Phase 0A.
