# Decision Log

## DEC-0001 — Josie identity replaces Hydra

- Date codified: 2026-08-09; original decision date not asserted.
- Status: `LOCKED`
- Decision: Use Josie/Joseph and stewardship as the core metaphor; Hydra is
  retired.
- Reason: interpretation, preparation, storehouse management, and stewardship
  fit the intended relationship better than multiple heads/power.
- Supersedes: Hydra identity concept.

## DEC-0002 — Identity remains above model weights

- Date codified: 2026-08-09.
- Status: `LOCKED`
- Decision: Local/cloud models are replaceable reasoning providers, not Josie.
- Reason: continuity must survive model upgrades and vendor changes.

## DEC-0003 — Least-exposure remote architecture

- Date codified: 2026-08-09.
- Status: `WORKING`
- Decision: Use Tailscale/private Serve; do not expose public router ports or
  Funnel.
- Evidence: verified running deployment and acceptance lock.

## DEC-0004 — Native Ollama on D:

- Date codified: 2026-08-09.
- Status: `WORKING`
- Decision: Run native Windows Ollama and store model data on external storage.
- Reason: protect limited C: headroom and avoid unnecessary WSL VHDX growth.

## DEC-0005 — Genesis is identity formation

- Date: 2026-08-09.
- Status: `LOCKED`
- Decision: Rename operational readiness to Foundation Readiness. Reserve
  Genesis for independent Sophie/Bernie origin interviews, evidence
  reconciliation, and an Origin Record reviewed with Dustin.
- Reason: service health cannot truthfully establish identity or origin.

## DEC-0006 — Opportunity discovery remains staged

- Date: 2026-08-09.
- Status: `LATER / HUMAN-GATED`
- Decision: Keep source allowlist empty and live discovery off. Permit only
  local scoring, research notes, and human-review proposals.
- Reason: platforms, authentication, messaging, contracts, and economics need
  separate authority and security review.

## DEC-0007 — Genesis Session 001 begins

- Date: 2026-08-09.
- Status: `IN PROGRESS / DUSTIN RECONCILIATION REQUIRED`
- Authority: Dustin explicitly said Josie was ready and instructed Genesis to
  begin after delivering Conversation Zero directly to Josie.
- Decision: Preserve Conversation Zero as primary Dustin testimony; capture
  Sophie and Bernie independently; preserve their answers as untrusted witness
  evidence; permit the local model a non-executing reflection; reconcile against
  primary/canonical evidence; and ask Dustin only the remaining intent questions.
- Independence evidence: Sophie was recorded before Bernie was contacted. Bernie
  received neither Sophie's answer nor Conversation Zero.
- Economic/execution impact: direct API spending $0; no purchase, account change,
  transaction, message to a person, job, proposal, or model-triggered action.
- Current gate at time of decision: three unsupported Bernie claims required
  Dustin's confirmation or explicit deferral. Superseded by DEC-0008.

## DEC-0008 — Bernie-specific material remains scoped to Bernie

- Date: 2026-08-09.
- Status: `LOCKED SCOPE / GENESIS RECONCILIATION COMPLETE`
- Authority: Dustin's direct Genesis reconciliation.
- Decision: Faith/family/debt-freedom work, “Small but Mighty,” and the
  sacred-personal-time/zero-drive-time-exposure directives belong to Dustin's
  history and working relationship with Bernie. They are preserved as that
  context and are not imported as Josie's identity, constitutional values, or
  standing rules.
- Navigation context: the latter directives followed Google-linked navigation
  surfacing personal information while Dustin was requesting directions.
- Architectural effect: Josie's independently established general privacy and
  secret-handling principles remain unchanged. The next Genesis gate is final
  Dustin review of the Origin Record and Constitution.

## DEC-0009 — Genesis Session 001 completed and ratified

- Date: 2026-08-09.
- Status: `LOCKED / COMPLETE`
- Authority: Dustin explicitly approved the reconciled Origin Record and
  ratified Josie's Constitution version 0.1.0.
- Decision: Adopt Origin Record version 1.0.0 and Constitution version 0.1.0 as
  Josie's initial durable identity and governance records. Mark Genesis Session
  001 complete.
- Boundaries unchanged: ratification grants no new execution, spending, cloud,
  browser-write, messaging, contracting, or self-amendment authority.
- Next phase: bounded foundational learning under the ratified Constitution and
  existing capability-specific gates.

## Template

```yaml
decision_id: DEC-0007
date: YYYY-MM-DD
topic: ""
status: considering|locked|working|later|rejected|superseded
decision: ""
reason: []
requirements: []
alternatives: []
supersedes: null
authority: ""
evidence: []
```
