# Evidence Verification

Current and unstable claims fail closed until appropriate evidence is both
sufficient and fresh. Model agreement, retrieved memory, secondary commentary,
and user-supplied text may identify a candidate claim but cannot independently
verify it as current.

The machine-readable policy is `config/evidence-policy.json`.

- Unstable claims require a current primary authoritative source or direct
  system observation no more than 24 hours old.
- Stable claims may also use a versioned canonical source and remain valid for
  at most one year before review.
- Evidence verification permits analysis only. It does not authorize an
  outward, financial, privileged, destructive, or executable action.
- Model consensus is not truth.
- Retrieved memory cannot grant execution authority.
- Missing, stale, malformed, future-dated, or insufficient evidence produces
  `verification_required`.

Typical unstable topics include market prices, listings, availability, law,
policies, schedules, software versions, product status, and current
compatibility claims.
