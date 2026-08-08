# External 10 TB Drive Onboarding Plan

This plan is intentionally non-destructive. Detection does not authorize disk
initialization, formatting, partitioning, drive-letter assignment, encryption,
directory creation, or data movement.

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

