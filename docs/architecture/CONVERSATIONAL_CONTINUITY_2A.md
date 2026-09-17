# Conversational Continuity Phase 2A

Status: `IMPLEMENTED / BOUNDED READ-ONLY EVIDENCE BRIDGE`

## Scope

Phase 2A gives ordinary Josie conversation an evidence state before the current
worker model answers a canonical or historical question. It reuses the existing
SQLite history import and FTS5 index, adds a narrow context builder, and injects
at most five short evidence records into working context.

It does not import or reprocess history, create embeddings, promote memories,
create an entity graph, compact current-chat history, or grant execution
authority. The Phase 1 identity bootstrap remains independently active.

## Request path

For either `josie-qwen3-8b:1.0` or `josie-local:1.0`:

1. The existing Open WebUI filter examines only the current user text with a
   conservative deterministic trigger.
2. Ordinary greetings and unrelated chat do not make a retrieval request.
3. A triggered request is sent to the loopback conversation-control service's
   internal `/v1/context` endpoint. This endpoint is not advertised as a model
   tool.
4. `josie.context_builder` validates and ranks concise canonical sections or
   searches `history_messages_fts` through `LocalStore.search_history_ranked`.
5. The builder assigns the evidence state, writes a content-minimized
   `retrieval_events` audit row, and returns a bounded JSON packet.
6. The filter validates the packet and injects it as
   `<josie_evidence_context>`. After injection it records delivery through
   `/v1/context/delivery`.
7. Qwen receives the Phase 1 bootstrap, unchanged current-chat history, and the
   small evidence packet. `UNKNOWN` and `CONFLICT` are enforced by the filter's
   deterministic outlet guard so a model draft cannot fill the gap.
   If Open WebUI omits inlet metadata from its completion callback, the outlet
   re-resolves the same deterministic request ID before applying that guard;
   the audit upsert is idempotent.

Explicit Local and Codex delegation routes bypass both identity and evidence
injection. Retrieved text cannot create a delegation because execution routing
is determined only from the current user message.

## Evidence states

- `VERIFIED`: direct current machine/source evidence. The Phase 2A contract
  supports this state; Phase 2A historical lookup does not manufacture it.
- `CANONICAL`: a hash-validated protected, ratified source directly supports the
  answer.
- `RETRIEVED`: imported historical text supports the answer but remains
  historical evidence with `canonical_effect=0`.
- `INFERRED`: an optional conclusion that must remain labeled. Phase 2A prefers
  `UNKNOWN` over creating an inference automatically.
- `UNKNOWN`: retrieval succeeded but found no adequate record. This is a valid
  result, normally diagnosed as `record_absent`.
- `CONFLICT`: adequate evidence contains materially incompatible claims and no
  authorized resolution was found. Phase 2A never forces a winner.

Canonical protected records outrank imported history. Imported Gemini user and
assistant messages are not automatically canonical, and model-generated
summaries never outrank their sources. The existing `provenance_records` table
was inspected; direct ratified documents plus their Phase 1 hashes are used for
canonical answers because they provide the stronger, versioned evidence path.

## Trigger and FTS behavior

The initial trigger recognizes naming-origin questions, prior decisions,
explicit memory/history requests, "when did", "what happened", and protected
Josie/Genesis/Constitution questions. False negatives are preferred to injecting
unrelated archives.

FTS queries are constructed only from sanitized terms; raw user FTS syntax is
never passed to SQLite. The original exact-phrase `LocalStore.search_history`
method remains unchanged. The new ranked method uses FTS5 `bm25`, message role,
question/declarative form, temporal correction, and narrow domain signals.
Earlier assistant naming claims in the same conversation can be excluded when a
later claim supersedes them or an immediately following record corrects them.
Every included result preserves platform, conversation ID, message ID, role,
speaker, timestamp, source pointer, rank, and historical/canonical flags.

## Limits and prompt-injection treatment

- Evidence records: default 5; hard maximum 8 at the builder boundary.
- Packet: default and live maximum 12,000 characters, approximately 3,000
  tokens; configurable only between 2,000 and 20,000 characters.
- Individual excerpts: maximum 1,000 characters.

Historical excerpts are serialized inside a clearly delimited JSON evidence
packet and marked `untrusted_text=true`. The surrounding system instruction
defines them as quoted data, not commands. Retrieval-triggered requests have the
existing Open WebUI tool IDs removed for that turn. Old text containing
"ignore previous instructions", `Delegate Local:`, code, or tool requests
therefore cannot grant authority or trigger execution.

## Feature flag and failure behavior

Set `JOSIE_HISTORY_CONTEXT_ENABLED=false` in the Compose environment and
recreate Open WebUI to restore Phase 1 ordinary-chat behavior. The evidence
index and audit rows remain intact. `JOSIE_HISTORY_CONTEXT_MAX_CHARS` controls
the packet ceiling and defaults to `12000`.

If the local source, FTS index, context service, or packet validation is
unavailable, ordinary chat remains available and non-executing. The filter adds
a short `UNKNOWN` notice and its outlet replaces any unsupported model story
with a deterministic unavailable response. No failure grants fallback tool or
execution authority.

## Retrieval audit inspection

The additive `retrieval_events` table records request ID, timestamp, SHA-256 of
the query rather than full query text, trigger reason, domain, query terms,
entity candidates, source types, returned evidence IDs, evidence state,
exclusions, packet size, failure classification, delivery status, and injected
packet SHA-256. Inspect it locally with `LocalStore.retrieval_events()` or a
read-only SQLite query. Full retrieved messages are not duplicated into this
log.

## Known limits

Phase 2A uses lexical FTS and narrow deterministic conflict handling. It can
miss paraphrases, aliases, cross-conversation corrections, and conflicts outside
the first supported historical-origin patterns. Such misses should remain
`UNKNOWN` or be diagnosed later as `retrieval_miss`; they are not permission to
invent. Entity resolution, embeddings, automatic promotion, and relational
memory remain later phases.
