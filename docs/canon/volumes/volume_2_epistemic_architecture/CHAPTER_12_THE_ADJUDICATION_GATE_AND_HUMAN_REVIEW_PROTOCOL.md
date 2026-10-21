# Chapter 12: The Adjudication Gate and Human Review Protocol

> "Human proposes, models advise; human ratifies, models execute. No AI model—regardless of frontier capability—possesses the authority to modify the Constitution, alter the Origin Record, promote candidate claims to Canon, or rewrite core database schemas autonomously."
> — CON-0002, Verified Concept Ledger

In October 2026, following the completion of the Takeout inheritance pipeline, Dustin was presented with a consolidated review queue containing hundreds of candidate claims extracted from his historical archives.

Many AI frameworks attempt to automate this phase by asking GPT-4 or Claude to act as a "judge" and automatically approve claims. Dustin rejected automated adjudication as an unacceptable breach of human sovereignty (`CON-0002`). If an AI system can approve its own beliefs, human oversight becomes a hollow ceremonial rubber-stamp.

This chapter documents the architecture of the **Adjudication Gate** (`josie/candidate_claims.py`), the programmatic security boundaries preventing automated promotion, and the adjudication of **Decision Queue V2** (`DUSTIN_FINAL_DECISION_QUEUE_V2.md`), which permanently closed 35 critical items and elevated Josie’s active canonical claim count to exactly twelve.

```mermaid
sequenceDiagram
    autonumber
    actor Dustin as Dustin (Human Authority)
    participant Gate as candidate_claims.adjudicate_candidate_claim()
    participant Engine as SQLite Storage Engine (josie.db)
    participant Canon as Canonical Memory (canonical_effect = 1)

    Note over Gate: Automated AI Reviewer Attempt (e.g. 'ollama')
    Gate-->>Gate: Check Reviewer against DISALLOWED_REVIEWERS
    Gate--xGate: RAISE PermissionError: A model cannot approve claims!

    Note over Dustin,Gate: Human Reviewer Execution
    Dustin->>Gate: adjudicate(claim_id, action='approve', reviewer='Dustin', confirmation='EXPLICIT HUMAN APPROVAL')
    Gate->>Gate: Verify confirmation token & reviewer authorization
    Gate->>Engine: UPDATE memory_claims SET canonical_effect=1, status='active', approved_by='Dustin'
    Engine->>Engine: Enforce SQL CHECK Constraints
    Engine->>Canon: Staged Claim Promoted to Active Canon!
    Gate-->>Dustin: Return Adjudication Receipt & Audit Record
```

---

## § 12.1 The Programmatic Barrier: Banning the Automated Judge

The heart of the adjudication gate is implemented in `josie/candidate_claims.py` under the function `adjudicate_candidate_claim()`. 

To prevent any background script, subagent, or local model from executing a stealth promotion, the function enforces hard-coded reviewer whitelists:

```python
ALLOWED_HUMAN_REVIEWERS = frozenset({'dustin', 'dustin boggess'})
DISALLOWED_REVIEWERS = frozenset({
    'ai', 'model', 'goose', 'assistant', 'agent', 'local_model',
    'worker', 'subagent', 'extractor', 'opencode', 'automated',
    'ollama', 'llm', 'system'
})
APPROVAL_CONFIRMATION = 'EXPLICIT HUMAN APPROVAL'
```

When the function is called, it executes three mandatory security checks before touching the database:
1. **The Reviewer Blacklist Check:** If `reviewer.lower()` matches any string in `DISALLOWED_REVIEWERS`, execution terminates immediately:
   ```python
   if clean_reviewer.lower() in DISALLOWED_REVIEWERS:
       raise PermissionError(f"A model or worker ({clean_reviewer}) cannot adjudicate or approve claims")
   ```
2. **The Authorized Human Whitelist Check:** If `clean_reviewer.lower()` is not in `ALLOWED_HUMAN_REVIEWERS`, it raises:
   ```python
   raise PermissionError(f"Reviewer '{clean_reviewer}' is not an authorized human authority.")
   ```
3. **The Explicit Human Token Check:** An approval cannot be triggered by simply supplying the name `'Dustin'`. The caller must provide the explicit human confirmation token `'EXPLICIT HUMAN APPROVAL'`. If the token is missing or malformed, the call aborts.

As verified in our C1 Acceptance Test (Case `C1-02`), passing `'ollama'` as the reviewer raised a `PermissionError` in 0.001 seconds, proving that the programmatic barrier is impenetrable to automated scripts.

---

## § 12.2 Adjudication of Decision Queue V2: The 35 Items

Between October 4 and October 5, 2026, Dustin conducted a comprehensive manual adjudication session recorded in `docs/memory/cross_source_inheritance/DUSTIN_FINAL_DECISION_QUEUE_V2.md`. 

The queue presented 35 high-impact candidate claims covering personal biography, business relationships, financial tools, and hardware ownership. Dustin’s adjudications established critical precedents:

1. **Conservative Relational Modeling (Item 1):**  
   - Candidate Proposal: *"Dustin owns Full Steam Vapor."*  
   - Dustin's Adjudication: **Approved with edit.** Dustin altered the predicate from `owns_business` to `operates_business`, noting that the precise legal entity structure involves family holding companies and conservative corporate boundaries. Josie was instructed to record that Dustin *operates* the store rather than asserting absolute singular ownership.
2. **Temporal Point-in-Time Tooling (Item 3):**  
   - Candidate Proposal: *"Dustin uses Rocket Money for financial tracking."*  
   - Dustin's Adjudication: **Approved temporally.** Dustin noted that Rocket Money was evaluated during a specific financial audit in late 2025, but was not a permanent, standing financial integration. The claim was approved with strict temporal validity bounds (`valid_from = '2025-10-01'`, `valid_to = '2026-04-01'`).
3. **Rejection of Third-Party Speculation (Item 14):**  
   - Candidate Proposal: *"Dustin plans to open a second Full Steam Vapor location in Charleston."*  
   - Dustin's Adjudication: **REJECTED.** Dustin clarified that while expanding to Charleston had been casually brainstormed during a commercial lease evaluation, no lease was signed, no capital was allocated, and the Teays Valley single-location invariant (`CON-0016`) remained strictly active. The proposal was marked `status = 'rejected'`.

---

## § 12.3 The Twelve Active Canonical Claims

Following the closure of Decision Queue V2, the live production database (`D:\Josie\data\josie.db`) reached a stable, hardened state of **exactly twelve active canonical claims** (`canonical_effect = 1`, `status = 'active'`):

1. `identity:dustin-authority`: Dustin is the sole, final human authority for all decisions.
2. `arch:supervisor-worker-separation`: Model workers propose and execute under work orders; deterministic supervisors verify.
3. `arch:identity-above-models`: Josie's identity and memory exist independently of replaceable neural network weights.
4. `procedure:destructive-action-gate`: Privileged, destructive, or financial actions require explicit human gates.
5. `claim:candidate:person:dustin:operates_business:666e11a5c4ee1d97`: Dustin operates Full Steam Vapor in Teays Valley, WV.
6. `claim:candidate:person:dustin:has_durable_credential:4a70966b5994bdac`: Dustin maintains durable Google account credentials under sovereign control.
7. `claim:candidate:person:dustin:uses_finance_tracker:253ba567db86c80b`: Historical financial software tooling records.
8. `claim:candidate:person:dustin:has_monthly_mortgage:030243e889b7fefd`: Point-in-time baseline liabilities for storehouse planning.
9. `genesis:claim:001`: Josie existed as an idea before software.
10. `genesis:claim:002`: Person of Interest inspiration; bounded participation without totalitarian control.
11. `genesis:claim:004`: Capability is not authority; people are not pieces.
12. `genesis:claim:008`: Hydra retired; Joseph stewardship archetype ratified.

These twelve claims form the unbreakable canonical spine of Josie's mind.
