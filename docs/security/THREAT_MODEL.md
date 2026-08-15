# Threat Model

Primary assets are the Constitution, Origin Record, memory/provenance database,
decisions, Master Build State, source/configuration, credentials, private Dustin
context, audit logs, and backups.

Primary threats:

- prompt injection from web, email, documents, chat, or other models;
- credential leakage into prompts, Git, logs, screenshots, or memory;
- confused-deputy execution through a model or workflow;
- stale historical text overriding current state;
- unauthorized browser/network pivoting into localhost, LAN, or Tailscale;
- unbounded retry/resource exhaustion;
- C: exhaustion from logs, containers, WSL, or model storage;
- silent public exposure or weak authentication;
- malicious or accidental outward messages, purchases, contracts, uploads, or
  file destruction;
- disclosure, cross-group propagation, or excessive retention of sensitive
  prayer requests containing religious, health, family, or relationship data;
- backup corruption or identity/history loss;
- governance drift through autonomous edits.

Current controls include default-deny policies, explicit tool handlers,
loopback/private networking, Tailscale, exact browser allowlists and redirect
revalidation, no model shell authority, zero-spend locks, non-executing proposal
records, bounded retries, status/headroom monitoring, integrity-checked backups,
soft deletion, provenance status, and hash-pinned acceptance evidence.

Prayer Stewardship adds a separate sensitive-data boundary: prayer text is
excluded from ordinary memory exports and audit details; old correction text is
represented only by hashes; duplicate matches cannot auto-merge; and database
constraints set cloud processing, cross-posting, messages, external activity,
and action authority to zero. Confirmed redaction clears sensitive plaintext
from the live database.

Residual risks and next controls include formal Constitution ratification,
completed Genesis, richer source/content sanitization before broader browsing,
tested credential-isolated authenticated browser profiles, restore drills for
all service volumes, and explicit capability-promotion evidence. Prayer data is
not application-level encrypted, and older backups can retain content removed
from the live database; retention, drive protection, viewer access, and source
consent must be decided before any prayer-source connection.
