# Google Takeout Reconnaissance — Phase 1

Status: dry run complete; production import locked.

## Evidence boundary

`D:\Josie-Storage\GoogleTO` was treated as immutable source evidence. The scan
inventoried every file recursively, hashed each archive with SHA-256, and read
ZIP central directories without bulk extraction. No source file was renamed,
moved, modified, or extracted in place.

The ten files total 302,262,938,079 bytes. Their filenames show five Takeout
batches, with batch 2 split into six ZIP parts. Because all files were present
together, their content namespaces are complementary, and no ZIP member path is
duplicated across archives, Phase 1 treats them as one source export set. Its
reproducible identity is
`e42d53b1e50a279148664d755e1f190666c16316899f5b137d194cf0acc6aed2`.

The complete per-file path, size, timestamp, hash, type, and central-directory
counts are in `GOOGLE_TAKEOUT_PHASE1_MANIFEST.json`.

## Actual Gemini source

Gemini evidence occurs only in `takeout-20260825T192605Z-4-001.zip`:

- `Takeout/Gemini/gemini_gems_data.html` — 11 bytes, no records.
- `Takeout/Gemini/gemini_scheduled_actions_data.html` — 11 bytes, no records.
- `Takeout/My Activity/Gemini Apps/MyActivity.html` — 6,944,510 bytes of
  UTF-8 Google My Activity HTML.
- 1,281 attachment members in DOCX, JPG, M4A, MP4, PDF, PNG, WAV, XLSX, and ZIP
  formats. These were listed but not extracted.

Only the three HTML members were selectively staged under
`D:\Josie-Storage\staging\history-inheritance-0.1\google-takeout-20260825`.
The parser reads only the Gemini Apps `MyActivity.html` path and fails closed for
other Takeout products.

The activity HTML is a newest-first stream of 2,711 cards. A `Prompted` card can
contain the account owner's prompt, a localized timestamp with its effective
timezone abbreviation, an optional Gemini response, a Gemini app URL containing
the conversation ID, and relative attachment references. Google did not supply
conversation titles or source message IDs in this file. Non-prompt cards are
activity evidence—assistant-feature use, selected actions, feedback, Gemini Apps
use, and Canvas creation—not dialogue.

## Dry-run normalization

The dry run found 2,588 prompt cards and 123 non-dialogue activity cards. It
normalized 5,108 historical records: 2,588 user messages, 2,397 Gemini messages,
and 123 activity events, grouped under 990 source conversation IDs. There are 191
prompt cards without an exported response. No missing response, title, message ID,
or outcome is fabricated.

The UTC date range is 2025-05-15T01:09:21Z through 2026-08-25T19:27:15Z. The
dry run found zero malformed records and zero normalized-message duplicates. It
identified 1,037 direct attachment references. Faithfully rendered raw text is
approximately 3,417,646 UTF-8 bytes; the structured source HTML is 6,944,510 bytes. Attachment
payloads are excluded from Phase 1 import estimates.

## Foundation and inheritance constraints

The new parser preserves source platform, archive and member hashes, source path
and pointer, conversation ID, nullable title/message ID, UTC and original
timestamps, speaker/role, text, source order, chronological message order, card
checksum, text checksum, stable dedupe identity, and attachment references.

The existing SQLite engine now has normalized, platform-neutral history run,
source, conversation, message, import-provenance, and attachment tables plus FTS5
search. Database checks force imported records to remain historical-only with no
canonical effect. Re-import deduplication and transaction rollback are covered by
isolated fixtures. There is intentionally no production import CLI in Phase 1.

Imported conversation evidence will not change `memories`, canonical/current
state, authority, or project completion. Plans remain evidence of plans—not proof
of outcomes—and repeated exploration is not commitment.

## Explicit exclusions

Google Photos (the six batch-2 ZIPs), Mail, YouTube/YouTube Music, Drive, every
non-Gemini product path in the mixed archive, and all Gemini attachment payload
content are outside this checkpoint. No ChatGPT parser was created because no
actual ChatGPT export was supplied.

## Next step (not performed)

After Dustin reviews this manifest and the attachment policy, create a fresh
database checkpoint and run one approval-gated production import from the staged,
checksum-verified `MyActivity.html`. The production step should record a manifest
run, insert the 5,108 historical records in one transaction, verify counts and
FTS retrieval, confirm zero canonical changes, and retain the source archives
unchanged. Attachment payload inspection/import remains a separate decision.
