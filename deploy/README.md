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

## Native local model

Ollama is deliberately not inside Docker on this 128 GB system. The verified
standalone Windows runtime is installed under
`D:\Josie-Storage\apps\Ollama\0.32.5`, and all model blobs are stored under
`D:\Josie-Storage\models\ollama`.

The governed `josie-local:1.0` model is derived from
`qwen2.5:1.5b-instruct-q4_K_M`. Its Modelfile fixes a 4096-token context, three
inference threads, and low-temperature output. The server allows one loaded
model, one parallel request, and a bounded queue.

Open WebUI reaches native Ollama at `host.docker.internal:11434`. Windows
Firewall retains default inbound blocking and adds one program-specific allow
rule limited to the observed Docker/WSL source networks. No LAN or Tailscale
client is authorized to call Ollama directly. OpenAI remains disabled.

## Storage headroom workflow

`n8n/workflows/storage-headroom-guard.json` is the canonical first workflow. A
host-side monitor refreshes a bounded JSON snapshot on D: every five minutes.
n8n may read only the staging directory, checks the snapshot daily, and records
a failed workflow execution when C: is below the configured headroom threshold.
The workflow has no HTTP, messaging, command, SSH, browser, or credential node.

n8n environment access is blocked. Execute Command, Local File Trigger, and SSH
nodes are explicitly excluded. Import the canonical workflow with the n8n CLI,
publish its stable ID, restart n8n, and verify it with the internal validation
trigger. The workflow never receives model-generated parameters.

## Open WebUI proposal boundary

The approved `proposal-interface` Compose profile is active and registered in
Open WebUI through ignored local environment configuration. When explicitly
started, it adds a dependency-free OpenAPI record server to an internal Docker
network shared only with Open WebUI. It publishes no host port, requires a
random bearer token stored outside Git on D:, accepts only `kind` and `summary`,
and writes only three allowlisted review proposal kinds. It has no process,
shell, tool, queue, transaction, messaging, or cloud execution capability.

Open WebUI uses it as a backend/global OpenAPI tool because the private service
name is reachable only from the Open WebUI container. The approved activation
script rebuilds this registration from the protected D: credential without
printing it or relying on a saved Admin UI override. See
`docs/OPENWEBUI_CORE_BRIDGE.md` for the exact start, stop, and recovery sequence.

## Recovery

Stop services with `docker compose --env-file deploy/.env.services -f deploy/compose.yaml down`.
Named volumes are retained. Remove no volumes unless a verified backup exists
and Dustin explicitly approves deletion.

The native model is replaceable download data. Backups record its installed
manifest and checksum but do not duplicate model blobs on the same external
drive.
