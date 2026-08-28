# Pre-GPU backup and recovery checklist

Audit date: 2026-08-28. Existing checkpoints are preserved. This pass verified existing SQLite copies without creating a new production checkpoint, stopping services or changing retention. A code commit is not a complete data backup.

## What is actually verified now

| Evidence | Result |
| --- | --- |
| C:/Josie/data/backups/josie-2026-08-28.db | 14,000,128 bytes; read-only quick_check OK; restored into RAM, full integrity_check OK; 39 tables |
| D:/Josie-Storage/backups/josie-database/josie-2026-08-28.db | Same size; read-only quick_check OK; restored into RAM, full integrity_check OK; 39 tables |
| D:/Josie-Storage/backups/services/open-webui-20260826-065537.tgz | Existing 1,011,223,952-byte full archive with checksum sidecar; older than current WebUI/delegation setup |
| D:/Josie-Storage/backups/services/n8n-20260826-065537.tgz | Existing 754,128-byte archive with checksum sidecar |
| D:/Josie-Storage/backups/open-webui-v0.8.9-pre-upgrade-20260826-221447/open-webui-data.tar.gz | Existing 1,011,234,728-byte WebUI pre-upgrade archive; not a current-version full recovery point |
| Older Phase 2 paired DB checkpoints and Git tags | Preserved; do not prune |
| Independent/off-device backup and current full-system image | Not verified |
| Current full-service restore at v0.11.1 | Not established by this pass |

SHA-256 of the daily SQLite copies:

- Local: `da94f2e3440c68a8cc42ca3281792743922d06f4e908629df87beee7c9127230`.
- External: `9fe0b80007ad9c64c4e12a44a67d160d55c7ec55d27501559d129f956522abc6`.

They are sequential snapshots, not byte-identical replicas: normal backup/audit timing differs. At the earlier count check their main records agreed; audit counts were 4,063 versus 4,064. Neither was substituted for production. Today's source files could change if the monitor is restarted; compare fresh hashes before reuse.

## Before installing hardware/software

- [ ] Create a fresh paired, labeled SQLite checkpoint using the existing process; integrity-check and restore-test both copies.
- [ ] In an approved quiet maintenance window, capture **current** WebUI and n8n volumes with matching image pins and configuration.
- [ ] Verify archive hashes/listings; restore-test separately, never over live state.
- [ ] Preserve Git history/tags plus the current uncommitted Compose change and untracked phone proof. Do not assume the new documentation commit includes them.
- [ ] Securely back up secrets/configuration separately from public documentation.
- [ ] Copy critical recovery artifacts to an independent device/location. D: is both source storage and backup storage, not offsite protection.
- [ ] Verify Windows recovery access and a current system-image/restore strategy before driver changes. A restore point does not back up chats.
- [ ] Record hashes, dates, image/runtime versions, backup destinations and successful restore results in the upgrade record.

### Existing SQLite checkpoint command — writes backup/audit records

Use immediately before the future upgrade, not as a read-only health check:

```powershell
Set-Location C:/Josie
.venv/Scripts/python.exe core.py backups create-checkpoint --label pre-rtx3060
```

It reuses existing local/external paths and creates non-deleting labeled checkpoints. The daily monitor separately keeps seven daily copies. Use SQLite backup/restore machinery, not a casual live .db copy that omits WAL state.

### Existing service backup helper — interrupts WebUI/n8n

```powershell
& C:/Josie/scripts/Backup-JosieServices.ps1
```

**Do not run unattended during active work.** It stops WebUI/n8n, uses temporary helper containers from already pinned images, archives the existing volumes, validates archive listings and writes SHA-256 sidecars/model listing. Its finally block runs Compose up for those services, which may also apply current Compose changes. Inspect current Git/config state and ensure pinned images/volumes are present before authorizing this maintenance window.

The helper was **not executed** in this documentation pass. It does not include all secrets, code, worker receipts or Windows state. An archive listing/hash does not itself prove application restore.

## What must be included

| Location | Why it matters / handling |
| --- | --- |
| C:/Josie tracked tree and .git | Code, scripts, tests, protected rules, model/deployment definitions, recovery tags/history |
| Uncommitted/untracked operator artifacts | Current deployment may differ from HEAD; save a scoped diff plus actual files |
| C:/Josie/.env and deploy/.env.services | Secrets and current image/config pins; encrypt, restrict access, never paste contents |
| C:/Josie/config and deploy | Policies, Compose, WebUI filters/config helpers, n8n definitions, browser/proposal sources, OpenCode config |
| C:/Josie/data/josie.db | Main memories/history/consultants/maintenance/audit data; use SQLite-consistent backup |
| josie_open_webui_data | WebUI DB/chat JSON, accounts, model/functions, assets; full volume required |
| josie_n8n_data | Workflow DB, execution/configuration/encryption state |
| C:/Josie/data/private | Service tokens/source config, job receipts and runtime state; credentials protected |
| C:/Josie/data/tools/gemini-cli | Existing package/lock/version and installation provenance |
| D:/Josie-Storage/apps | Pinned Ollama and OpenCode runtimes |
| D:/Josie-Storage/models/ollama | Models/manifests and custom aliases; no need to redownload as a repair |
| D:/Josie-Storage/GoogleTO, ChatGPTTO, staging | Immutable export/source/provenance evidence; do not rewrite or re-extract |
| D:/Josie-Storage/proposals, status, secrets | Operational data and separate service credentials |
| D:/Josie-Storage/backups and C:/Josie/data/backups | Existing recovery generations, manifests/hashes and preserved drills |
| C:/Users/dusti/.codex and .gemini | Authentication/configuration; prefer secure account recovery, never publish tokens |
| C:/Users/dusti/.ollama | Existing native Ollama user configuration/state |
| C:/Users/dusti/.wslconfig and AppData/Roaming/Docker/settings-store.json | Current Docker/WSL resource and startup behavior |
| Task Scheduler /Josie definitions and relevant startup shortcuts | Hidden launch order; export definitions securely before future edits |
| Tailscale service/Serve configuration and account recovery | Private access route; preserve authorized settings securely, do not copy node keys into docs |
| Docker C: VHDX | Whole-disk recovery only with Docker properly stopped and a consistent snapshot process; do not copy a live VHDX as your only backup |
| Windows recovery/driver information | OS recovery if a driver fails; separate from application data |

WebUI/n8n encryption/authentication keys must travel securely with the matching data. Possession of a DB without required keys/configuration may not restore access. Do not rotate/regenerate keys just to simplify a backup.

## Restore acceptance, not just “file exists”

A good recovery package can recover code, configuration **and** data. For the future maintenance window:

1. Verify checksums and expected sizes; keep originals immutable.
2. Restore SQLite into an isolated target; check integrity, expected tables/counts, histories and consultant/maintenance records.
3. Restore a service archive into an isolated recovery volume with the matching image/configuration; verify sign-in, chat histories and function/tool records.
4. Confirm no secrets were included in public reports and no production volumes were overwritten.
5. Record the successful recovery location/method and operator sign-off before GPU work.

Never downgrade an old WebUI image against today's migrated production volume. Never use Docker prune/down -v, Git history rewrites or backup deletion to make space for the upgrade.
