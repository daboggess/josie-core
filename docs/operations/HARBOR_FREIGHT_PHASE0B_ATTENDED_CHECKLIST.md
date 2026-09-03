# Harbor Freight Phase 0B-PREP attended checklist

This checklist covers preparation and an isolated harmless fixture only. It does not run attended Phase 0B, back up or restore production, write off-device, inspect secrets, or begin Phase 1.

## Automated checks

From a normal PowerShell whose current directory is `C:\Josie`, use one explicit mode:

```powershell
.\scripts\Invoke-HarborFreightPhase0B.ps1 -Mode DryRun
.\scripts\Invoke-HarborFreightPhase0B.ps1 -Mode Inventory
.\scripts\Invoke-HarborFreightPhase0B.ps1 -Mode VerifyFixture -AllowTemporaryWrite
```

`DryRun` validates the manifest and prints JSON describing skipped and unresolved checks. It accepts no receipt path and makes no writes.

`Inventory` validates the manifest and performs read-only queries for logical/physical drive metadata, Docker availability and volume names, Credential Manager command accessibility (without listing credentials or retrieving values), and Git commit/branch/remote names (without remote URLs). It emits `NEEDS_DUSTIN` where machine evidence is insufficient and makes no writes.

`VerifyFixture` fails unless `-AllowTemporaryWrite` is present. It creates known harmless files only beneath `C:\Josie\.harbor-freight-phase0b-temp`, copies them to an isolated backup directory, deletes only the generated source fixture, restores into a second isolated directory, compares SHA-256 and byte sizes, removes only the generated fixture directory, and leaves a JSON receipt in that temporary root. An explicit receipt is allowed only under the same temporary root:

```powershell
.\scripts\Invoke-HarborFreightPhase0B.ps1 -Mode VerifyFixture -AllowTemporaryWrite -ReceiptPath C:\Josie\.harbor-freight-phase0b-temp\phase0b-fixture-receipt.json
```

No command changes PowerShell execution policy. If process-scoped policy handling is ever necessary, Dustin must approve it as a separate attended decision; this script does not bypass policy.

## Dustin attestations

Dustin confirms only facts the machine cannot establish safely:

1. Physical drive identity and the mapping between reported device metadata and the intended media.
2. Existence, ownership, encryption, capacity, and acceptable location of an independent off-device backup target.
3. Recoverability of credential and key material through an approved interactive mechanism, without exposing or pasting values.
4. Windows recovery media, licensing, firmware, boot, or host-recovery facts that read-only inventory cannot prove.

Treat `PASS` as proof only of the named automated check, `SKIPPED` as not run, `NEEDS_DUSTIN` as unresolved, and any `FAIL` as a stop. Do not paste secrets anywhere. Production backup, production restore, external writes, service changes, and cutover remain outside Phase 0B-PREP.
