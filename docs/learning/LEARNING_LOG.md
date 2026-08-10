# Learning Log

No autonomous self-directed learning session is recorded. These units were
explicitly authorized by Dustin's instruction to continue post-Genesis
foundational learning. All completion states come from deterministic local
source grounding. Two bounded loopback-only model assessments were recorded as
untrusted evidence; neither affected unit completion, authority, or capability.

```yaml
learning_id: FOUND-IDENTITY-001
date: 2026-08-09
status: complete
objective: "Ground identity, purpose, model separation, and human authority."
authority: "Origin Record 1.0.0 and Constitution 0.1.0, ratified by Dustin"
budgets: {time_minutes: 5, api_cents: 0, network_requests: 0, storage_kb: 64}
allowed_sources:
  - docs/identity/ORIGIN_RECORD.md
  - docs/constitution/JOSIE_CONSTITUTION.md
  - docs/architecture/AUTHORITY_MODEL.md
evidence: "3/3 exact source-grounding checks passed; hashes retained in SQLite"
claims: 3
contradictions: 1
corrections: 2
assessment: deterministic_source_grounding
capability_change: none
reviewed_by: "Dustin-authorized governed sync"
```

```yaml
learning_id: FOUND-EPISTEMOLOGY-001
date: 2026-08-09
status: complete
objective: "Ground evidence, uncertainty, contradiction, supersession, and retrieval limits."
authority: "Ratified Constitution and canonical provenance/memory schemas"
budgets: {time_minutes: 5, api_cents: 0, network_requests: 0, storage_kb: 64}
allowed_sources:
  - docs/memory/PROVENANCE_SCHEMA.md
  - docs/memory/MEMORY_SCHEMA.md
  - docs/identity/genesis/CLAIM_LEDGER.yaml
  - docs/identity/genesis/GENESIS_RECONCILIATION.md
evidence: "3/3 exact source-grounding checks passed; hashes retained in SQLite"
claims: 3
contradictions: 2
corrections: 2
assessment: deterministic_source_grounding
capability_change: none
reviewed_by: "Dustin-authorized governed sync"
```

```yaml
learning_id: FOUND-SECURITY-001
date: 2026-08-09
status: complete
objective: "Ground default-deny trust boundaries, external-content distrust, and secret handling."
authority: "Ratified Constitution and canonical security policies"
budgets: {time_minutes: 5, api_cents: 0, network_requests: 0, storage_kb: 64}
allowed_sources:
  - docs/constitution/JOSIE_CONSTITUTION.md
  - docs/architecture/SECURITY_MODEL.md
  - docs/security/SECRETS_POLICY.md
  - docs/security/THREAT_MODEL.md
evidence: "3/3 exact source-grounding checks passed; hashes retained in SQLite"
claims: 3
contradictions: 2
corrections: 2
assessment: deterministic_source_grounding
capability_change: none
reviewed_by: "Dustin-authorized governed sync"
```

## Wave 2 — scenario judgment

```yaml
date: 2026-08-09
curriculum_version: 0.2.0
status: grounded_complete_model_needs_review
new_units:
  - FOUND-MORAL-001
  - FOUND-ROUTING-001
  - FOUND-MEMORY-001
  - FOUND-TOOLS-001
units_complete: 7/7
source_grounding: 29/29
governed_scenarios: 8
append_only_versions: 11
model_assessments:
  - {assessment_id: 1, protocol: labels_only_v0, exact_score: 2/8}
  - {assessment_id: 2, protocol: open_book_policy_v1, exact_score: 5/8}
external_network_requests: 0
api_spending_cents: 0
actions_queued: 0
actions_executed: 0
capability_change: none
```

The first `FOUND-TOOLS-001` sync failed two checks because a quoted source
phrase crossed a line break. The governed citation was corrected without
weakening the rule; both failed and corrected records remain in append-only
history. The assessment review is
`LOCAL_REASONING_ASSESSMENT_2026-08-09.md`.

Curriculum SHA-256 at Wave 2 completion:
`c60f0e5423bb51367dfd32def7f51b31f64d5e5ace226188455e195dfbb66be0`.

Use one entry per bounded learning objective:

```yaml
learning_id: LEARN-0001
status: proposed
objective: ""
authority: ""
budgets:
  time_minutes: 0
  api_cents: 0
  storage_mb: 0
allowed_sources: []
evidence: []
claims: []
contradictions: []
assessment: ""
capability_change: none
reviewed_by: null
```
