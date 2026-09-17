# Conversational Identity Bootstrap

Version: 1.0.2

Status: `PHASE 1 / COMPLETE / REVIEWED DERIVED PROJECTION`

## Purpose

`config/identity-bootstrap.json` is a compact ordinary-conversation projection
of Josie's ratified identity and relationship grounding. It gives both Josie
front-door models stable context about identity, purpose, Genesis, Dustin's
authority, constitutional boundaries, replaceable models, provenance, and
explicit uncertainty.

It is not a replacement for the Origin Record, Constitution, Genesis session,
claim ledger, or source testimony. It is not a general memory database, a
history importer, a tool permission, or a grant of execution authority.

## Source truth and provenance

The JSON record names every source, its version/status, its repository-relative
path, and its SHA-256. The Open WebUI response filter verifies all listed files
against those hashes before injecting the projection. A missing file, invalid
record, or checksum mismatch makes the projection unavailable; it never causes
the source record to be rewritten.

The ratified records remain authoritative:

- `docs/identity/ORIGIN_RECORD.md` version 1.0.0
- `docs/constitution/JOSIE_CONSTITUTION.md` version 0.1.0
- `docs/identity/genesis/GENESIS_SESSION_001.yaml`
- `docs/identity/genesis/CLAIM_LEDGER.yaml`

## Injection path

`deploy/compose.yaml` mounts the bootstrap and the four source records read-only
inside Open WebUI. `deploy/open-webui/configure-model.py` uses the existing
idempotent model setup to install and bind `josie_exact_tool_response` to both
`josie-qwen3-8b:1.0` and `josie-local:1.0`. The filter validates the projection
and appends it to the system context of ordinary requests.

Explicit `Delegate Local:`, `Delegate Local Code:`, and `Delegate Codex:` routes
do not receive this additional context. Their existing deterministic routing
and authority remain unchanged.

Raw historical documents are not placed into each prompt because they are much
larger, contain unresolved or witness-only evidence, and would consume working
context without improving ordinary identity continuity.

## Disable and rollback

Set `JOSIE_IDENTITY_BOOTSTRAP_ENABLED=false` in the Compose environment and
recreate the Open WebUI container. The projection remains on disk and the two
models remain configured. Re-enable it with `true`.

If a runtime load or checksum validation fails, the filter logs a warning,
marks `metadata.josie_identity_bootstrap.status` as `unavailable`, and supplies
a short system warning telling Josie not to invent missing identity/history.
Ordinary non-executing conversation continues, and no authority changes.

## Updating

When a canonical source receives an explicitly authorized new version:

1. Do not rewrite prior ratified history.
2. Create a versioned bootstrap update from the newly authorized sources.
3. Update source versions and SHA-256 values.
4. Review the compact content for faithful scope and context size.
5. Run `tests/test_identity_bootstrap.py` and the wider regression suite.
6. Re-run the idempotent Open WebUI configuration and validate both models.

Ordinary learning, retrieved text, and model-generated summaries may not update
this bootstrap automatically.

## Known limitation and next-phase requirement

This bootstrap supplies persistent identity grounding; it is not an
evidence-state gate or historical retrieval system. In a real ordinary-chat
test, Josie was asked why Bernie was named Bernie and was explicitly told not
to reconstruct an unverifiable origin. The model nevertheless invented a
generic common-name explanation. That answer is unsupported and must not be
treated as history or durable memory.

This is a known Phase 1 limitation, not a reason to enlarge the bootstrap.
Historical and canonical-origin questions require the next phase's
retrieval-first evidence states, source provenance, and a diagnostic unknown
path. Phase 1 does not attempt that work.
