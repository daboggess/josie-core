# Candidate Claims Architecture (Phase 3B)

Memory Vault Phase 3B establishes the formal boundary between unverified historical evidence and Josie's canonical beliefs.

## Core Epistemic Pipeline

```
Raw Historical Evidence (history_messages)
       │
       ▼
Extraction Engine (LocalModelClaimExtractor / StubClaimExtractor)
       │  [Fail-Closed Validation Layer]
       ▼
Candidate Claims (memory_claims status='candidate', canonical_effect=0)
       │  [Preserves full claim_evidence links, role weighting, timestamps]
       ▼
Human Adjudication Gate (Dustin explicit review)
       │  [EXPLICIT HUMAN APPROVAL required; models cannot approve]
       ▼
Approved Canonical Knowledge (memory_claims status='active', canonical_effect=1)
       │
       ▼
Deterministic Task Priming (PrimingManifest -> PrimingBundle)
       │
       ▼
Worker Execution (Prompt Contract v1)
```

## Epistemic Rules

1. **A model may PROPOSE a claim. A model may NOT APPROVE a claim.**
2. **Historical evidence may SUPPORT or CONTRADICT a candidate. Historical evidence may NOT become canonical merely because it exists.**
3. **Required separation**:
   `RAW EVIDENCE != CANDIDATE CLAIM != APPROVED / CANONICAL CLAIM != PRIMED WORKER CONTEXT`
4. **Candidate claims must default to non-canonical**:
   - `status = 'candidate'`
   - `canonical_effect = 0`
   - `approved_by = NULL`
   - `reviewed_at = NULL`
   - Excluded from all ordinary worker prompt contract priming.

## Persistence Architecture

Phase 3B reuses the existing SQLite schema directly without migrations:

- `memory_claims`: Holds both candidate and active canonical claims.
  - `status`: `'candidate'`, `'active'`, `'disputed'`, `'superseded'`, `'rejected'`.
  - `canonical_effect`: Strictly `0` for candidates; `1` only when `status='active'` and `approved_by` is populated.
- `claim_evidence`: Holds provenance links connecting claims to `history_messages(message_id)`.
  - `relation_type`: `'supports'`, `'contradicts'`, `'derived_from'`, `'related_to'`, `'supersedes'`, `'refines'`.
  - Captures `role`, `speaker`, `source_timestamp`, `source_pointer`, and excerpt hash.
- `entities`: Referential integrity for `subject_entity_id`.
- `audit`: Immutable record of candidate staging, review actions, and promotions.

## Stable Identity and Deduplication

Candidate claims derive a deterministic stable ID from semantic proposition content:
```
claim:candidate:{subject_entity_id}:{predicate}:{normalized_value_hash}
```
Where `normalized_value_hash` is computed from Unicode NFKC, lowercased, whitespace-collapsed proposition text.

- **Re-discovery**: When the same proposition appears across multiple messages, exactly ONE candidate claim is maintained, and multiple distinct `claim_evidence` rows are attached.
- **Contradictions**: When different values are stated for the same subject/predicate (e.g. "no NVIDIA GPU" vs "has RTX 3060"), they produce separate candidate claims with distinct IDs. They are never silently merged.

## Evidence Attribution and Role Decoupling (Phase 3B.1)

A core vulnerability identified in Real Memory Pilot 001 is that provider envelope roles do NOT automatically equal semantic claim authority:
- Historical messages authored by a user may contain pasted AI output (e.g. Dustin copying a ChatGPT response into a Google Messages turn).
- External historical cloud assistants (e.g. Gemini Apps) were offering recommendations in 2025 and must not be conflated with the Josie architecture (`system:josie`).

Phase 3B.1 decouples provider envelope roles from semantic authority via a strict 4-class attribution taxonomy:

| Attribution | Description | Evidence Class | Base Confidence | Max Authority |
|---|---|---|---|---|
| `direct_user_assertion` | Direct statement spoken by Dustin | `RETRIEVED` | 0.85 – 1.0 | Primary |
| `assistant_assertion` | Assertion by external conversational assistant | `INFERRED` | <= 0.60 | Secondary |
| `quoted_or_pasted_content` | Quoted, forwarded, or pasted AI/external text | `INFERRED` | <= 0.60 | Secondary |
| `ambiguous_source` | Mixed, unattributed, or unclear provenance | `INFERRED` | <= 0.50 | Context Only |

### Deterministic Attribution Rules:
1. **Envelope Role Decoupling**: Envelope `role == 'user'` alone NEVER confers primary authority if the content contains pasted assistant markers (e.g. `gpt response`, `chatgpt:`, blockquotes `> `). It is classified as `quoted_or_pasted_content`.
2. **Identity Separation**: Gemini output maps to `assistant:gemini`, ChatGPT output maps to `assistant:chatgpt`. Neither is ever assigned to `system:josie`.
3. **Fail-Closed Weighting**: In `evaluate_evidence_weight()`, only verified `direct_user_assertion` references receive primary confidence (`RETRIEVED`). Quoted, pasted, or assistant assertions are strictly capped at `confidence <= 0.60` with `evidence_class = 'INFERRED'`.

## Span-Level Evidence Attribution (Phase 3B.2)

Phase 3B.1 operated at whole-message granularity. However, real historical transcripts frequently exhibit single-turn polysemy: a user turn may interleave direct human assertions with pasted external AI responses.

For example, in Message 485:
- Spans 15..85: `"Btw i am a+ certified with years of experience with commercial servers"` (Dustin's authentic voice and qualification).
- Spans 87+: `"Alright Soph, here’s the real truth..."` followed by `"Your parts on hand (... RTX 3090 ...)"` (Pasted ChatGPT output hallucinating an RTX 3090).

Whole-message attribution either stripped Dustin of primary credit for his genuine statements or falsely elevated pasted ChatGPT text to human authority. Phase 3B.2 introduces fine-grained, deterministic span attribution.

### Span Data Model & Schema

The `claim_evidence` table is extended with deterministic character offset bounds:
```sql
ALTER TABLE claim_evidence ADD COLUMN span_start INTEGER DEFAULT NULL;
ALTER TABLE claim_evidence ADD COLUMN span_end INTEGER DEFAULT NULL;
```
Correspondingly, `EvidenceReference` supports `span_start: int | None = None` and `span_end: int | None = None`.

### Bounded Deterministic Segmentation

Without relying on nondeterministic LLMs or heavy NLP libraries, `get_pasted_regions(raw_text)` scans message text for:
1. Markdown blockquotes (`> `)
2. Fenced quote/code blocks (```` ``` ````)
3. Assistant persona openings (e.g., `"Alright Soph"`, `"Sophie (me"`, `"I’m going to show you"`)
4. Explicit AI tool headers (e.g., `"ChatGPT:"`, `"Claude:"`, `"Gpt response"`)

Any span within these identified offset ranges is classified as `quoted_or_pasted_content` (or `assistant_assertion` if from an assistant). Spans outside these regions in user turns retain `direct_user_assertion`.

### Fail-Closed Validation Invariants

1. **Offset Invariants**: Offsets must satisfy `0 <= span_start <= span_end <= len(raw_text)`. Any invalid offset fails closed.
2. **Verbatim Excerpt Matching**: The excerpt must exist verbatim in `raw_text`. When span offsets are provided, `raw_text[span_start:span_end]` must match the excerpt. Fabricated or loose excerpts are rejected.
3. **Epistemic Authority Clamping**: `validate_proposal()` rejects or clamps any attempt by a model to attribute `direct_user_assertion` to a span overlapping a pasted/quoted region.
4. **Distinct Multi-Span Evidence Keys**: Provenance IDs incorporate span offsets (`history:{mid}:{span_start}:{span_end}`), allowing multiple distinct spans from the same message to serve as independent evidence references.

## Adjudication & Promotion Gate

Human review actions:
- `approve`: Requires explicit reviewer identity (`reviewer='Dustin'`) and confirmation (`EXPLICIT HUMAN APPROVAL`). Verifies existing candidate state, non-empty evidence links, and valid structure. Sets `status='active'`, `canonical_effect=1`, `evidence_class='CANONICAL'`. Preserves all historical evidence links.
- `reject`: Sets `status='rejected'`, `canonical_effect=0`. Provenance links remain permanently intact.
- `dispute` / `needs_review`: Sets `status='disputed'`, `canonical_effect=0`.
- `supersede`: Marks prior claim as `status='superseded'` by a successor claim. The superseded record is preserved, never deleted.
- `defer`: Leaves candidate in review queue.

Models and workers are explicitly forbidden from acting as reviewers or approvers.

## Canonical Priming Isolation

Candidate claims, rejected claims, and disputed claims are strictly excluded from normal canonical queries (`KnowledgeQuery(statuses=("active", "confirmed"))`) and never enter `PrimingBundle`s generated for worker tasks.

Strict 5-condition priming isolation:
1. `pending` / `candidate` (`canonical_effect=0`): Excluded.
2. `rejected` (`canonical_effect=0`): Excluded.
3. `needs_review` / `disputed` (`canonical_effect=0`): Excluded.
4. `superseded` (`canonical_effect=0`): Excluded.
5. ONLY `approved` / `active` (`canonical_effect=1`, `evidence_class='CANONICAL'`, `approved_by` populated): Included in priming manifests and bundles.

## Claim Taxonomy and Memory Layer Mapping

Phase 3B formalizes 13 allowed claim categories with deterministic mapping to SQLite memory layers:

| Category | Description | Underlying Memory Layer |
|---|---|---|
| `profile` | Dustin's identity, preferences, roles | `identity` |
| `identity` | Josie / Bernie / system identity attributes | `identity` |
| `preference` | General behavioral and styling preferences | `relational` |
| `relationship_context` | Working dynamics between human and system | `relational` |
| `decision` | Settled technical and project decisions | `semantic` |
| `project_state` | Current milestone, build, and repository state | `semantic` |
| `hardware` | Physical host hardware, GPUs, specs | `semantic` |
| `general` | Cross-cutting facts and assertions | `semantic` |
| `procedure` | Step-by-step operating guidelines | `procedural` |
| `recurring_task` | Scheduled, repetitive workflows | `procedural` |
| `constraint` | Hard architectural or constitutional rules | `procedural` |
| `architecture` | Subsystem topology, boundaries, and contracts | `procedural` |
| `lesson` | Post-mortem learnings and observed bugs | `episodic` |

## Bounded Evidence Bundle Contract

To guarantee bounded context windows and deterministic runtime limits:
- `DEFAULT_MAX_BUNDLE_MESSAGES`: 50 messages per extraction batch.
- `DEFAULT_MAX_BUNDLE_CHARS`: 25,000 characters per bundle.
- `DEFAULT_MAX_MESSAGE_CHARS`: 2,500 characters per message.
- Batch processing uses `split_evidence_bundle(messages, max_messages=50, max_chars=25000)` to deterministically partition large evidence streams.

## CLI Usage Reference

The candidate claims system provides a deterministic CLI via `python -m josie.candidate_claims`:

```bash
# Inspection / dry-run extraction (zero database writes)
python -m josie.candidate_claims extract --dry-run --rule-based --limit 25

# Live candidate staging (persists non-canonical review candidates: status='candidate', canonical_effect=0)
python -m josie.candidate_claims extract --stage --rule-based --limit 25

# List candidates in the review queue
python -m josie.candidate_claims list --status candidate --limit 25

# Inspect a specific candidate claim with full evidence excerpts
python -m josie.candidate_claims inspect <claim_id>

# Show full provenance chain back to source history_messages
python -m josie.candidate_claims show-provenance <claim_id>

# Explicit human approval (promotes to canonical_effect=1; requires explicit reviewer AND confirmation token)
python -m josie.candidate_claims approve <claim_id> --reviewer Dustin --confirmation "EXPLICIT HUMAN APPROVAL" --reason "Verified from logs"

# Approval with explicit supersession of an older claim
python -m josie.candidate_claims approve <claim_id> --reviewer Dustin --confirmation "EXPLICIT HUMAN APPROVAL" --supersedes <old_claim_id> --reason "Policy updated"

# Human rejection (sets status='rejected', canonical_effect=0, keeps provenance)
python -m josie.candidate_claims reject <claim_id> --reviewer Dustin --reason "Disproved by benchmark"

# Mark as needs-review / disputed
python -m josie.candidate_claims needs-review <claim_id> --reviewer Dustin --reason "Requires reproduction"

# Verify canonical store and priming eligibility
python -m josie.candidate_claims verify-canonical <claim_id>
```

## Section K Synthetic History Reference Fixture

The test suite includes a comprehensive lifecycle and temporal evolution fixture (`test_24_synthetic_history_fixture_full_lifecycle_and_temporal_evolution`) verifying:
1. **Raw Evidence**:
   - `Msg 1` (2026-08-01): `"For coding tasks, use OpenCode as the primary coding worker."`
   - `Msg 2` (2026-08-15): `"Update policy: Goose is primary; OpenCode is fallback."`
   - `Msg 3` (2026-08-20): `"Remember our test policy: Do not let NOT_RUN win a result gate."`
2. **Extraction & Staging**: All 3 messages extracted into distinct candidate claims (`status='candidate'`, `canonical_effect=0`, `approved_by=NULL`).
3. **Priming Isolation**: None of the pending candidates enter worker priming bundles.
4. **Approval & Priming**: Approving `Msg 1` claim promotes it to `canonical_effect=1`; enters architecture priming.
5. **Temporal Supersession**: Approving `Msg 2` claim with `supersedes_claim_id=claim_1` sets `Msg 2` active (`canonical_effect=1`) and transitions `Msg 1` to `superseded` (`canonical_effect=0`). Architecture priming delivers `Msg 2` and strictly excludes `Msg 1`. Evidence rows for `Msg 1` remain 100% intact.
6. **Procedure Promotion**: Approving `Msg 3` claim promotes it to `canonical_effect=1`, primed under procedure.

## Phase 3B.3 Temporal and Durability Semantics

Phase 3B.3 establishes the distinction between permanent identity/profile facts, point-in-time states, and evolving goals or preferences.

### Durability Taxonomy
Every candidate claim proposal, staged candidate record, and canonical memory claim specifies a `durability`:
1. `durable`:
   - Facts expected to remain true indefinitely unless explicitly updated or superseded.
   - Examples: technical certifications (CompTIA A+), multi-year commercial server experience, identity traits.
2. `current_state`:
   - Point-in-time assertions describing transient or evolving empirical conditions.
   - Examples: physical hardware inventory ("owns two 4TB NVMe drives"), negative hardware status ("does not own an RTX 3090"), current machine configuration.
   - **Key Invariant**: Hardware ownership and lack of hardware are empirical point-in-time states; they MUST NEVER be treated as timeless `durable` identity.
3. `preference`:
   - Goals, strategies, preferences, or target outcomes that may evolve over time.
   - Examples: "seeks cheapest hardware setups to accomplish AI goals", preferred worker choices.
4. `transient`:
   - Ephemeral task, session, or momentary situational states that should generally not become long-lived canonical knowledge.

### Temporal Bounds
- `valid_from`: Point-in-time timestamp (ISO 8601 UTC) from which the assertion is known to be valid. Automatically grounded in the supporting evidence's `source_timestamp` when not explicitly overridden.
- `valid_until` / `valid_to`: Upper temporal bound after which the assertion is no longer assumed to hold.
- `supersedes_claim_id` / `superseded_by_claim_id`: Explicit pointers tracking claim lineage upon human adjudication.

### Invariants Maintained
- **Human Authority**: Models may infer or propose durability and temporal bounds, but cannot promote any claim to canonical truth. Dustin remains the sole approval authority.
- **Priming Isolation**: Regardless of durability classification (`durable`, `current_state`, etc.), unadjudicated candidate claims have `canonical_effect=0` and are strictly excluded from priming bundles.
- **No Autonomous Conflict Resolution**: Contradictory claims (e.g. past hardware presence vs later hardware absence) remain staged as distinct candidates for explicit human review. No autonomous model resolution is permitted.
