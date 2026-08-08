# Josie origin and provenance workflow

Josie must preserve where a project fact came from and whether Dustin confirmed
it. Imported conversations and model statements are evidence, not authority.

## Status rules

- `unverified`: recorded from a conversation, model, document, or recollection.
- `confirmed`: Dustin explicitly confirmed the statement.
- `rejected`: Dustin explicitly said the statement is wrong or obsolete.

No record may become confirmed merely because multiple models repeat it.
Corrections append a new audit event; material deletion or bulk import requires
human approval.

## Origin interview queue

1. What problem was Josie originally intended to solve?
2. Which decisions came directly from Dustin, and which were suggestions?
3. Why were the names Josie, Sophie, and Bernie chosen?
4. Which safety and spending rules are permanent?
5. What may Josie do autonomously when Dustin is unavailable?
6. Which past decisions are obsolete or still disputed?
7. Which private conversations may be imported, and at what level of detail?
8. What does “Josie 1.0 is alive” mean as a verifiable acceptance test?

Answers are recorded locally with a source label and remain unverified until
Dustin confirms them. Sophie and Bernie may be interviewed only through an
explicitly approved cloud interaction or through text Dustin supplies locally.

## Initial organized history

`PROJECT_HISTORY_SEED.json` contains eight narrowly scoped statements taken
from Dustin's setup brief, approvals, constraints, running checklist, and the
Bernie review that Dustin relayed. They are imported as `unverified`; the source
bundle is tracked in Git so the local database entries are reproducible and
auditable. Use `origin records`, then `confirm origin N` or `reject origin N` in
Josie's local GUI. No record is auto-confirmed.
