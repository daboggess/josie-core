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

Docker was initially stopped. After its existing verified installation was
started, the read-only internal report showed:

- three in-use image layers totaling about 12.61 GB unique data;
- active volume data of about 1.13 GB, almost entirely Open WebUI state;
- container writable layers below 0.12 GB total;
- 3.54 GB of build cache reported as reclaimable.

No file, image, volume, cache, log, backup, or virtual disk was deleted, moved,
compacted, or modified. The four existing Josie containers recovered and
reached healthy state.

Conclusion: C: has adequate headroom today, but Docker's virtual disk is the
first storage item to investigate if free space resumes declining. Build-cache
pruning is the clearest possible first recovery (about 3.54 GB as observed), but
it can make later image rebuilds slower and remains a separate destructive
choice. Any cache/image/volume cleanup, Docker data relocation, or VHDX compaction is a separate
state-changing maintenance action and requires an attended review of exact
targets and recoverability.
