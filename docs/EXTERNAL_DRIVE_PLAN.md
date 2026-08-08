# External 10 TB Drive Onboarding Plan

This plan is intentionally non-destructive. Detection does not authorize disk
initialization, formatting, partitioning, drive-letter assignment, encryption,
directory creation, or data movement.

## Verified onboarding state — 2026-08-07

- Disk 1: UnionSine USB 3.2, 9.1 TiB reported by Windows.
- GPT partition table, NTFS volume `D:`, label `External HDD`.
- Windows reports Healthy / Online / OK.
- Approximately 8.82 TiB free at onboarding.
- Existing personal and backup folders were preserved.
- The isolated `D:\Josie-Storage` tree was created without altering other content.

## Read-only acceptance checks

1. Confirm the USB disk is physically detected and is at least 8 TB as reported by Windows.
2. Record model, health, operational state, partition style, read-only state, filesystem, and capacity.
3. Confirm the disk is not the Windows boot or system disk.
4. Determine whether existing data must be preserved before proposing changes.
5. Run a read-only health check before any write operation.

## Proposed directory layout

```text
Josie-Storage\
  models\
  datasets\
  downloads\
  generated\
  archives\
  backups\
  logs-archive\
  staging\
```

Keep active applications, the SQLite database, and current logs on the internal
SSD where practical. Use the external disk for large, replaceable, archival, or
backup-oriented data.

## Approval boundary

After detection, Josie must present the exact disk number, reported capacity,
existing partition/filesystem state, and preservation risk. Any initialization,
formatting, encryption, or data migration requires a new explicit human approval.
