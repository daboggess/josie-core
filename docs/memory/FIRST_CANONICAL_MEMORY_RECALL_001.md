# First Real Canonical Memory Promotion and Recall Test Receipt

**Document Version:** 1.0.0  
**Phase:** Memory Vault — Real Memory Recall Loop  
**Date:** 2026-09-26  
**Subject:** `person:dustin`  
**Predicate:** `has_durable_credential`  
**Repository:** `D:\Josie`  
**Branch:** `reconcile/live-work-20260917`  

---

## 1. Executive Summary

This receipt documents the successful end-to-end execution of the first real canonical memory loop in Josie Core:

$$\text{Raw Evidence} \longrightarrow \text{Span Attribution} \longrightarrow \text{Candidate Claim} \longrightarrow \text{Durability Classification} \longrightarrow \text{Human Adjudication} \longrightarrow \text{Canonical Knowledge} \longrightarrow \text{Deterministic Priming} \longrightarrow \text{Worker Execution}$$

Under explicit human authority from Dustin, exactly **ONE** real historical memory claim was promoted from candidate state to canonical knowledge:
> *"Dustin is A+ certified with years of experience with commercial servers."*

All remaining 4 candidate claims in the review queue (hardware inventory, lack of RTX 3090, cost-optimization preference) remained strictly unapproved (`canonical_effect=0`).

A fresh recall test was dispatched through Josie's deterministic supervisor execution path. The worker received the newly promoted memory inside the immutable Prompt Contract, successfully answered the recall question, satisfied all machine acceptance criteria with zero scope violations, and emitted an authoritative supervisor receipt (`PASS`).

---

## 2. Promoted Canonical Claim Specification

| Field | Value |
|---|---|
| **Claim ID** | `claim:candidate:person:dustin:has_durable_credential:4a70966b5994bdac` |
| **Subject Entity ID** | `person:dustin` |
| **Predicate** | `has_durable_credential` |
| **Value Text** | `A+ certified with years of experience with commercial servers` |
| **Memory Layer** | `semantic` |
| **Pre-Approval Status** | `candidate` (`canonical_effect=0`, `evidence_class=RETRIEVED`) |
| **Post-Approval Status** | `active` (`canonical_effect=1`, `evidence_class=CANONICAL`) |
| **Authority Scope** | `canonical:decision` (promoted from `candidate:decision`) |
| **Confidence** | `1.0` (High) |
| **Confidence Basis** | Direct user statement in historical conversation (primary evidence) |
| **Durability** | `durable` |
| **Valid From** | `2025-11-27T19:27:57Z` |
| **Valid To** | `None` (unbounded permanent credential) |
| **Superseded By** | `None` (net-new canonical memory) |

### Evidence Span Provenance

| Field | Value |
|---|---|
| **Evidence ID** | `history:histmsg_fc3209a8f43e1b31d5d4d1457497d3c54c250c39aaffefc8acc2dff9141bf2fd:15:85` |
| **Platform** | `google_gemini` (Google Takeout) |
| **Conversation ID** | `86be169449008c68` (Conversation 57) |
| **History Message ID** | `485` |
| **Timestamp** | `2025-11-27T19:27:57Z` |
| **Provider Envelope Role** | `user` |
| **Provider Envelope Speaker**| `google_account_owner` |
| **Span Attribution** | `direct_user_assertion` |
| **Span Range** | `[15..85]` in raw text |
| **Verbatim Span** | `"Btw i am a+ certified with years of experience with commercial servers"` |
| **Excerpt SHA-256** | `f36d350361b8ceb96f6aef76393ff2ced24dbab99f4132297bd6d7ed6c7cfa30` |
| **Source Pointer** | `Takeout/My Activity/Gemini Apps/MyActivity.html#activity-card-2424:0` |

---

## 3. Human Adjudication Gateway Execution

The single candidate claim was adjudicated via `josie.candidate_claims.adjudicate_candidate_claim`:

- **Authorized Reviewer:** `Dustin`
- **Confirmation Token:** `EXPLICIT HUMAN APPROVAL`
- **Adjudication ID:** `adj:claim:candidate:person:dustin:has_durable_credential:4a70966b5994bdac:1f03b2ab3c00`
- **Adjudication Timestamp:** `2026-09-26T19:33:43+00:00`
- **Reason:** `Explicit human approval for verified durable credential claim`
- **Audit Table ID:** `4370` (`event: candidate_claim_approved`)
- **Database Status:** `data/josie.db` committed atomically.

---

## 4. Pre-Approval vs. Post-Approval Priming Verification

Deterministic priming was audited before and after approval using `josie.knowledge.assemble_priming_from_knowledge`:

### Category `('decision',)`
- **Pre-Approval Bundle Hash:** `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` (0 items, empty)
- **Post-Approval Bundle Hash:** `36e3a71bce3eb2f1f41559e4b31e1fbd40e5ed6b544a061c04aa5c870b37d5c7` (1 item)
- **Item Included:** `claim:candidate:person:dustin:has_durable_credential:4a70966b5994bdac`
- **Cryptographic Hash Drift:** `True` (proved live database promotion effect)

### Category `('identity', 'decision')`
- **Pre-Approval Bundle Hash:** `61d361d9a5b3a322bb2b453e025f190eec26042dbaf98889980d2977b3117fe2` (1 item: `identity:dustin-authority`)
- **Post-Approval Bundle Hash:** `a7b3101575feb22018e12e1e75a8ca59206abe6d05cf375c9a64512211fe3e06` (2 items)
- **Items Included:**
  1. `claim:candidate:person:dustin:has_durable_credential:4a70966b5994bdac`
  2. `identity:dustin-authority`
- **Cryptographic Hash Drift:** `True`

### All Categories `()`
- **Pre-Approval Bundle Hash:** `785d038f6bfe0f85b678c187be09a3dc554fa6aa07fe3042456f9ffdbcb53086` (3 active seeds)
- **Post-Approval Bundle Hash:** `70259942591176c90b01a0d1eefeb9956d946cca222c9f518bd9d074a59fe512` (5 canonical records)
- **Cryptographic Hash Drift:** `True`

---

## 5. Supervisor Execution & Worker Recall Receipt

A real worker job was executed through the qualified local supervisor pipeline:

| Field | Value |
|---|---|
| **Job ID** | `first-canonical-memory-recall-001` |
| **Receipt ID** | `7524bf51-1303-476d-954d-a85b6313a234` |
| **Receipt Path** | `D:\Josie\scratch\first_canonical_recall_workspace\receipts\7524bf51-1303-476d-954d-a85b6313a234.json` |
| **Workspace** | `D:\Josie\scratch\first_canonical_recall_workspace` |
| **Harness** | `opencode` (1.18.23) |
| **Agent Profile** | `josie-coder` (`D:\Josie\.opencode\agents\josie-coder.md`) |
| **Model** | `ollama/qwen3:14b` |
| **Final Status** | `PASS` |
| **Reason** | `PASS` |
| **Elapsed Seconds** | `53.1s` |
| **Priming Bundle Hash** | `c3cef8ce5a9fed931c2fb701a17e00b99fba3cf3fcc02fc82b865496516d11c7` |
| **Manifest Hash** | `e70cd390b5bbb0fe9447b5aaf0c1de50c33a622d76fc3988a1f4be87e97e9d34` |
| **Primed Item IDs** | `["claim:candidate:person:dustin:has_durable_credential:4a70966b5994bdac"]` |

### Prompt Contract Injection Evidence

The Prompt Contract compiled deterministically with the primed canonical knowledge bound to `RESOURCE RULES`:

```text
RESOURCE RULES
Local resources only. Do not use paid/cloud providers or download models.
Task-relevant evidence:
- [claim:candidate:person:dustin:has_durable_credential:4a70966b5994bdac] A+ certified with years of experience with commercial servers
```

### Worker Output & Verification

- **Target Output File:** `D:\Josie\scratch\first_canonical_recall_workspace\answer.md`
- **Output Content:**
  ```text
  A+ certified with years of experience with commercial servers
  ```
- **Machine Acceptance Evaluation:**
  - `file_exists` (`answer.md`): `PASSED`
  - `changed_paths` (`answer.md` only): `PASSED`
  - `no_unexpected_files`: `PASSED`
  - `scope_violations`: `[]` (0 violations)

---

## 6. Negative Control & Contamination Audit

An automated audit of `data/josie.db` verified zero contamination across the storage layers:

| Metric | Before Adjudication | After Adjudication | Delta |
|---|---|---|---|
| **Active Canonical Claims (`canonical_effect=1`)** | 4 | **5** | **+1** |
| **Candidate Claims (`canonical_effect=0`, `status='candidate'`)** | 5 | **4** | **-1** |
| **Rejected Claims (`canonical_effect=0`, `status='rejected'`)** | 1 | **1** | **0** |
| **Total Memory Claims** | 10 | **10** | **0** |

### Remaining Unapproved Candidate Queue
The remaining 4 candidate claims in the queue remain untouched and unpromoted:
1. `claim:candidate:person:dustin:current_state:065e9148e20a8e85` — owns two 4TB NVMe drives and two 24TB HDDs (`durability=current_state`, `canonical_effect=0`)
2. `claim:candidate:person:dustin:current_state:58256dc9b4be1c96` — does not own an RTX 3090 (`durability=current_state`, `canonical_effect=0`)
3. `claim:candidate:person:dustin:has_current_state:44862d9673362fee` — does not own RTX 3090 (`durability=current_state`, `canonical_effect=0`)
4. `claim:candidate:person:dustin:preference:5d3b7ea34b6b8949` — seeks cheapest hardware setups to accomplish AI goals (`durability=preference`, `canonical_effect=0`)

### Contamination Invariants Confirmed
- $\checkmark$ **NO hardware claims promoted** (RTX 3090 absence and drive inventory remain unapproved candidates).
- $\checkmark$ **NO preference claims promoted** (budget optimization goal remains unapproved candidate).
- $\checkmark$ **NO transient claims promoted**.
- $\checkmark$ **Zero candidate leakage** into priming bundles or active canonical storage.
- $\checkmark$ **Human authority audit log** records event `4370` with authorized reviewer `Dustin`.

---

## 7. Test Suite Status

- `tests.test_candidate_claims`: **65/65 PASS**
- Full test discovery (`tests/test_*.py`): **422/422 PASS**
- `git diff --check`: **0 errors**
