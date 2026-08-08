# Browser capability review

## Decision

Browser execution remains disabled. The approved allowlist is currently empty.
This is intentional: no concrete website workflow has yet justified the risks
of navigation, credentials, uploads, downloads, or form submission.

The current machine-readable policy is `config/browser-policy.json`:

- default deny and `enabled: false`;
- no allowed hostnames and no wildcard support;
- navigation, extraction, form entry, downloads, and uploads disabled;
- loopback, private-network, and Tailscale destinations blocked;
- redirects may not escape a future explicit allowlist;
- page text, hidden text, scripts, and model-facing extracts are untrusted;
- dedicated APIs and installed connectors are preferred;
- access-control, CAPTCHA, anti-bot, impersonation, credential-exfiltration,
  and model-direct-execution bypasses are prohibited.

The browser worker itself still exposes only `/health`; every other request
returns 403. Merely editing the policy cannot enable execution because the
worker contains no navigation route.

## Requirements for a future site approval

Before adding one hostname, Dustin must approve:

1. the exact hostname and business purpose;
2. whether login or personal data is involved;
3. which read-only or outward actions are needed;
4. whether a dedicated connector or API is safer;
5. what confirmation is required before forms, messages, uploads, or downloads;
6. a data-retention and credential-handling rule;
7. a test proving redirects and private-network access remain blocked;
8. an expiration or review date for the allowlist entry.

Until that attended review occurs, `core.py browser status` must report
`locked`, zero allowed hosts, and zero external activity.
