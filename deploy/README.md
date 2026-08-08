# Josie service deployment

This directory is intentionally safe to prepare while unattended. It does not
start services, expose LAN ports, spend cloud credits, or accept arbitrary shell
commands.

## Human gate

The one grouped attended step enables/updates WSL, installs Docker Desktop in
per-user WSL 2 mode, completes any required reboot, and signs Tailscale in. Do
not disable UAC or make the current administrator account auto-login.

After the gate, the deployment controller verifies exact container image
digests and creates `deploy/.env.services`. Only then may services be pulled and
started. All published ports bind to `127.0.0.1`; remote exposure requires a
separate explicit approval.

## Recovery

Stop services with `docker compose --env-file deploy/.env.services -f deploy/compose.yaml down`.
Named volumes are retained. Remove no volumes unless a verified backup exists
and Dustin explicitly approves deletion.
