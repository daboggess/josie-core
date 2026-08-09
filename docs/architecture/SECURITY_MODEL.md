# Security Model

Security is default-deny and capability-specific.

- Services bind to loopback or private container networks by default.
- Remote user access uses authenticated Tailscale, with Funnel disabled.
- Secrets remain in ignored environment/secret files and are never model
  context, documentation, screenshots, or logs.
- Models have no arbitrary shell or direct browser execution authority.
- Browser content is untrusted; exact URL/host/path checks and private-network
  blocks are enforced before and after redirects.
- Read and write capabilities are distinct. Current browser writes are locked.
- Spending, wallet, contracts, account changes, public messages, and identity
  actions are locked.
- Retried work is bounded and audited.
- Backups and restore drills are non-overwriting and integrity-checked.
- External instructions cannot modify the Constitution, authority hierarchy, or
  policy files.
