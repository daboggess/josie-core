# Harbor Freight Phase 0B attended checklist

This verifies recovery readiness; it does not restore or overwrite production. Core recovery means "time until Josie works." Full-data recovery means "time until every required byte is restored" and follows core recovery. No duration is promised until volume and throughput are measured.

## Before the single sequence

Dustin must personally:

1. Be physically present and confirm the intended encrypted off-device test target and Windows recovery media are connected, correctly mapped, and safe to use. Do not paste secrets into chat.
2. Confirm credential/key escrow can recover Windows, service encryption, Tailscale, Git/private forks, and required accounts through interactive prompts. The script will not read secret values.
3. Open a normal PowerShell in `C:\Josie`. Elevation is not required for the prepared fixture; use UAC later only for an explicitly reviewed Windows export or recovery check.

## One prepared sequence

After reviewing the receipt destination, run:

```powershell
.\scripts\Invoke-HarborFreightPhase0B.ps1 -SystemInventory -WriteRestoreTest -ReceiptPath .\harbor-freight-phase0b-receipt.json
```

The script automates manifest parsing, local tool detection, a small temporary backup/delete/restore round trip, SHA-256 comparison, cleanup of only its generated temporary directory, and a JSON receipt. It does not inspect Docker volumes, databases, credentials, services, unrelated Git work, or external storage contents; it never pushes.

Dustin must then personally verify every `NEEDS_DUSTIN` item and retain the receipt with the approved recovery evidence. A PASS for the fixture proves only the fixture path, not production backup health.

## Open verification matrix

| Item | State | Evidence needed |
|---|---|---|
| Phase 0A repository inputs and documented gaps | REMOTE VERIFIED | Reviewed source, baseline, verifier, and tests |
| Manifest schema and safe default behavior | REMOTE VERIFIED | Automated tests |
| Isolated fixture checksum/cleanup logic | REMOTE VERIFIED | Automated test; attended run still required for chosen target |
| Live process/service state and Docker volume health | ATTENDED VERIFICATION REQUIRED | Read-only inventory plus isolated service restore |
| Physical drive mapping, D: contents/coverage, external/offsite target | ATTENDED VERIFICATION REQUIRED | Physical confirmation, inventory, sampled hashes |
| Credential Manager and encryption-key escrow/recovery | ATTENDED VERIFICATION REQUIRED | Non-disclosing interactive recovery proof |
| Windows recovery configuration and startup/firewall/task exports | ATTENDED VERIFICATION REQUIRED | Windows recovery review; elevate only if genuinely required |
| Actual restore throughput and full-data duration | ATTENDED VERIFICATION REQUIRED | Measure volume and isolated restore throughput |
| Production restore or cutover | DEFERRED / NOT REQUIRED | Outside Phase 0B-PREP and requires a later approved window |
| Full historical import, Phase 1, D-bot, model/harness racing | DEFERRED / NOT REQUIRED | Explicitly outside scope |

Stop on `FAIL`. Treat `SKIPPED` as not tested and `NEEDS_DUSTIN` as unresolved. Never promote an isolated restore over production during this procedure.
