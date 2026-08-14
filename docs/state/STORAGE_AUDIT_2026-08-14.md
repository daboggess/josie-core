# Josie Storage Audit â€” 2026-08-14

Status: `READ-ONLY AUDIT / NO CLEANUP PERFORMED`

The Windows boot drive is 118.20 GB total with 42.48 GB free. The external
drive is 9,313.87 GB total with 9,014.84 GB free. Josie's critical threshold
remains 15 GB free on C:.

The largest known Josie-related consumer on C: is Docker Desktop's WSL storage:

- `C:\Users\dusti\AppData\Local\Docker`: 15.50 GB total;
- `C:\Users\dusti\AppData\Local\Docker\wsl\disk\docker_data.vhdx`: 15.39 GB;
- Docker logs: approximately 0.023 GB;
- `C:\Josie\data` and `C:\Josie\logs`: below 0.01 GB each;
- `C:\Josie\.venv`: approximately 0.01 GB.

Docker was not running during the audit, so its internal reclaimable-object
report was unavailable. No file, image, volume, log, backup, or virtual disk was
deleted, moved, compacted, or modified.

Conclusion: C: has adequate headroom today, but Docker's virtual disk is the
first storage item to investigate if free space resumes declining. Any image or
volume cleanup, Docker data relocation, or VHDX compaction is a separate
state-changing maintenance action and requires an attended review of exact
targets and recoverability.
