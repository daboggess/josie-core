# Josie incident and recovery runbook

These steps are deliberately local, bounded, and recoverable. Never delete
volumes, databases, backups, or external-drive folders during diagnosis.

## Normal start

1. Open `C:\Josie\Start Josie.cmd` or the Josie desktop shortcut.
2. Confirm the header says `HEALTH: OK` and `CLOUD LOCKED`.
3. Run `C:\Josie\.venv\Scripts\python.exe C:\Josie\core.py audit` for evidence.

## Normal stop

Close the Josie window. After container deployment, stop local services without
deleting data:

`docker compose --env-file C:\Josie\deploy\.env.services -f C:\Josie\deploy\compose.yaml down`

Do not add `--volumes`.

## If Josie will not start

1. Do not reinstall or delete the database.
2. Run the health check:
   `C:\Josie\.venv\Scripts\python.exe C:\Josie\core.py health --json`
3. Run the non-overwriting restore drill:
   `C:\Josie\.venv\Scripts\python.exe C:\Josie\core.py tools run restore-drill --json`
4. Export secret-free diagnostics:
   `C:\Josie\.venv\Scripts\python.exe C:\Josie\core.py tools run health --json`
5. Review `C:\Josie\logs\josie.log` without posting API keys or `.env` contents.

## Recovery boundaries

- The restore drill loads the newest backup into memory; it never overwrites the live database.
- A real restore requires Dustin's approval immediately before replacement.
- Preserve `C:\Josie\data\josie.db`, local backups, and `D:\Josie-Storage\backups`.
- Before a real restore, take an additional copy of the live database and verify both copies.
- Network exposure, firewall changes, Tailscale changes, and account sign-in require approval.
- If cloud spending unexpectedly appears enabled, close Josie and set
  `JOSIE_ALLOW_CLOUD=false` in the ignored `.env` before restarting.

## Git recovery

Known-good checkpoints are pushed to the private `josie-core` repository.
Never use destructive reset commands while uncommitted work exists. Inspect
`git status` and create a backup before reverting any tracked change.
