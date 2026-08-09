# Provenance Schema

Minimum claim record:

```yaml
claim_id: CLM-0001
claim: ""
status: unverified
source:
  kind: person|model|document|system_observation|retrieval
  identity: ""
  locator: ""
  captured_at: ""
evidence: []
confidence:
  level: unknown|low|medium|high
  basis: ""
conflicts_with: []
supports: []
supersedes: null
superseded_by: null
effective_from: null
effective_to: null
conclusion: null
unresolved_questions: []
confirmed_by: null
confirmed_at: null
```

Rules:

- Source identity and model output are evidence, never authority by themselves.
- Confidence must have a stated basis.
- Current state requires current evidence.
- Contradictions remain visible until explicitly reconciled.
- Temporal supersession does not destroy historical records.
- Dustin alone resolves uncertainty about Dustin's intentions.
