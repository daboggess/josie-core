# Attended local-service gate

Run this only after WSL and Docker are healthy. It requires exact version tags
and verified `sha256` image digests for n8n, Open WebUI, and Playwright. Mutable
tags such as `latest` or `main` are rejected.

The script writes the ignored `deploy\.env.services`, runs Josie's fail-closed
preflight, validates Compose, asks once, then pulls/builds/starts the stack.
Published ports remain bound to `127.0.0.1`. It does not configure Tailscale
exposure, enable browser navigation, unlock cloud providers, or add credentials.

Run under the same one-process PowerShell bypass described for the system gate.
The script itself does not change Windows execution policy.

Stop without deleting data using the exact command in
`docs\INCIDENT_AND_RECOVERY.md`. Never add `--volumes` during ordinary recovery.
