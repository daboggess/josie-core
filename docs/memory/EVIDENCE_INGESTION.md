# Raw Evidence Ingestion Architecture

Memory Vault Phase 3A establishes the ingestion foundation for historical conversation archives (ChatGPT / Sophie and Google Gemini / Bernie).

## Core Epistemic Distinction

The Josie memory architecture enforces a strict four-stage epistemic progression:

```
RAW EVIDENCE
     ≠
CANDIDATE CLAIM
     ≠
ADJUDICATED / CANONICAL KNOWLEDGE
     ≠
PRIMED WORKER CONTEXT
```

| Layer | State | SQLite Table | Effect on Current Truth | Execution / Prompt Authority |
|---|---|---|---|---|
| **Raw Evidence** | Historical event | `history_messages`, `history_conversations`, `history_sources` | **Zero** (`historical_only=1`, `canonical_effect=0`) | **Zero** (never in prompt contracts or memory_claims) |
| **Candidate Claim** | Extracted proposition | Future Phase 3B extraction table / staging | **None** (unreviewed proposal) | **Zero** |
| **Adjudicated Knowledge** | Vetted truth | `memory_claims` (`adjudication_status='approved'`) | **Active** current canonical truth | **High** (eligible for deterministic priming) |
| **Primed Context** | Bounded injection | `WorkOrder.priming_context` / Prompt Contract | **Contextual** bounded guidance | **Enforced** contract constraints |

### Epistemic Invariants

1. **Imported text is evidence, not truth**: What Dustin or an assistant once stated in a chat session is raw historical evidence. Importing it does not declare that statement to be current truth.
2. **Zero automatic claim creation**: Importing raw evidence writes exclusively to `history_*` tables. It **never** writes rows to `memory_claims` or `claim_evidence`.
3. **Zero automatic prompt contamination**: The front-door canonical priming pipeline (`assemble_priming_from_knowledge` / `load_knowledge_from_store`) queries only `memory_claims`. Raw evidence is completely invisible to normal worker priming.
4. **Historical immutability**: Source messages and conversations preserve original timestamps, provider-native IDs, speaker roles, and source file locations.

---

## Verbatim Raw Text vs Search Normalization

The architectural progression for textual fidelity is:

```
SOURCE ARCHIVE
     → verbatim extracted text (history_messages.raw_text)
     → optional deterministic search normalization (normalize_for_search)
```

- **Verbatim Raw Text (`history_messages.raw_text`)**:
  - Persisted text is the exact, verbatim textual payload extracted from the provider record.
  - **No NFKC normalization**: Ligatures (such as `ﬁ`), full-width characters (`Ｊｏｓｉｅ`), smart quotes, emoji, and exact spacing are preserved verbatim.
  - **No line-ending rewriting**: `\r\n`, `\r`, or `\n` present in the source are preserved as extracted.
  - `raw_checksum`: Computed directly as SHA-256 of the verbatim persisted `raw_text`.
- **Search Normalization (`normalize_for_search`)**:
  - An optional, deterministic helper for search queries and FTS indexing.
  - Standardizes line endings and applies Unicode NFKC normalization for search matching only.
  - **Never** stored as or substituted for authoritative raw evidence.

---

## Structured ChatGPT Parts & Reproducibility

Modern ChatGPT Takeout exports represent messages as nodes in a conversation DAG with structured `content.parts` arrays:

- **Flattened Textual Projection**:
  - `history_messages.raw_text` stores the verbatim concatenated textual payload of the message parts.
  - When messages contain single parts, this is identical to the part itself.
- **Complete Structural Reproducibility**:
  - The original structured provider message dictionary (including part boundaries, multimodal attachments, reasoning recaps, code execution blocks, author objects, and metadata) is preserved through cryptographic provenance:
    1. `source_archive` and `source_archive_sha256`: Fingerprints the immutable source ZIP/JSON.
    2. `source_pointer`: Locates the exact message within the member file (`{member}#{conversation_id}:{message_id}`).
    3. `source_record_checksum`: SHA-256 of the canonical JSON representation of the entire provider message node dictionary (`msg`).
  - Any consumer can verify or reconstruct the original multipart structure from the source archive using this tuple.

---

## Architecture & Storage Reuse

Phase 3A reuses Josie's existing normalized history schema without requiring schema migrations or parallel databases:

- `history_import_runs`: Auditable batch execution records, tracking status (`running`, `completed`, `rolled_back`), provider platform, source manifest SHA-256, and stats.
- `history_sources`: Archive and member file locators with exact SHA-256 fingerprints.
- `history_conversations`: Conversation threads with provider IDs, titles, and first/last message timestamps.
- `history_messages`: Individual messages with `stable_id`, `dedupe_key`, `raw_text`, `raw_checksum`, `source_record_checksum`, `role`, and `speaker`.
- `history_message_imports`: Audit links tying each message occurrence to its import run.
- `history_messages_fts`: Full-text search index across raw historical transcripts.

### Provenance Linkage for Future Phase 3B

When candidate claims are extracted in Phase 3B, they will link back to raw evidence via the existing foreign key in `claim_evidence`:

```
claim_evidence.history_message_id -> history_messages.message_id
```

---

## Provider Adapters

The ingestion system (`josie/evidence_ingestion.py`) defines a provider-neutral interface:

1. **`ChatGPTTakeoutAdapter`**:
   - **Supported inputs**: ZIP archives (containing `conversations.json` or multipart `conversations-*.json`), standalone JSON files, and unpacked export directories.
   - **Structure handling**: Traverses conversation mapping DAGs, resolves parent/child message trees, extracts roles (`user`, `assistant`, `system`, `tool`), parses multimodal and thought blocks, preserves float/integer/ISO timestamps.
   - **ID format**: `stable_id = msg_chatgpt_{source_conv_id}_{source_msg_id}`, `dedupe_key = openai_chatgpt:{source_conv_id}:{source_msg_id}`.

2. **`GeminiTakeoutAdapter`**:
   - **Supported inputs**: Takeout ZIP archives and standalone `MyActivity.html` exports.
   - **Structure handling**: Parses Google My Activity HTML cards, maps `Prompted <text>` to user message and answer text to assistant message, extracts Gemini conversation URLs.
   - **ID format**: Preserves Gemini activity card IDs and dedupe keys.

---

## Production Run-ID Safety Rules

Production and test run IDs undergo strict validation in `LocalStore._import_history_records`:
- **Length**: Must be between 1 and 120 characters (`len <= 120`).
- **Traversal Prevention**: Prohibits consecutive dots (`..`) and leading/trailing dots.
- **Character Whitelist**:
  - Test mode: `r"test[-_][A-Za-z0-9._-]{1,119}"`
  - Production mode: `r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}"`
- **Strictly Disallowed**: Path separators (`/`, `\`), leading/trailing whitespace, and shell metacharacters (`;`, `$`, `&`, `|`, `<`, `>`, `` ` ``, `'`, `"`).

---

## Safety, Idempotency & Rollback

- **Preflight dry-run**:
  - `dry_run_evidence_ingest` inspects archives, parses records, and checks against database keys without performing any SQLite writes (`writes_performed = 0`).
  - If target DB does not exist, dry-run does not create it.
- **Idempotency & Replay**:
  - Re-running the same archive detects zero new records (`messages_would_insert = 0`).
  - Returns `idempotent_replay = True` and skips creating unnecessary checkpoint backups.
- **Conflict Detection (Fail-Closed)**:
  - If incoming evidence has identical stable ID / dedupe key but differing `raw_checksum` from existing records, ingestion is immediately aborted to prevent silent mutation or corruption of historical evidence.
- **Transactional safety**:
  - Ingestion runs inside a SQLite transaction (`BEGIN IMMEDIATE`).
  - Any parse error, constraint conflict, or simulated failure cleanly rolls back all table mutations and records an auditable `rolled_back` run status.
