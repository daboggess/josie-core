# Gemini Historical Ingestion & Extraction Summary

**Repository:** `daboggess/josie-core` (`D:\Josie`)  
**Status:** COMPLETE  
**Production Extractor:** `LocalModelClaimExtractor(qwen3:14b)` on local Ollama (`http://127.0.0.1:11434`)  
**Date:** 2026-10-04  
**Runtime:** 159.4 minutes across 20 units  
**Hardware Profile:** NVIDIA RTX 3060 12GB (Local GPU, temp ~40-52°C)  

---

## 1. Corpus Reconciliation Audit

- **Total Ingested Gemini Conversations in Corpus:** 990 / 990 (100% accounted for)
- **Total Ingested Gemini Messages in Database:** 5,108 (4,985 conversational, 123 activity cards)
- **Total Gemini User Messages:** 2,588
- **Extraction Units Executed:** 20 / 20 units
- **Smart Extraction Windows Processed:** 403 optimal batches (compressed from 1,118 raw chunks)
- **Extraction Failures / Unprocessed Units:** 0

---

## 2. 18-Point Extraction Funnel Cumulative Totals

| Step | Metric | Total |
|---|---|---|
| 01 | source_conversations_processed | 990 |
| 02 | textual_messages_processed | 4985 |
| 03 | user_messages_processed | 2588 |
| 04 | raw_model_proposals | 201 |
| 05 | assistant_authority_rejections | 1 |
| 06 | entailment_rejections | 1 |
| 07 | hypothetical_fictional_rejections | 10 |
| 08 | event_preference_rejections | 0 |
| 09 | transient_noise_suppression | 33 |
| 10 | historical_only_routing | 30 |
| 11 | duplicate_corroborating_evidence | 0 |
| 12 | personal_memory_candidates | 75 |
| 13 | project_architecture_candidates | 10 |
| 14 | hardware_state_candidates | 34 |
| 15 | runbook_procedural_candidates | 6 |
| 16 | sensitive_review_candidates | 0 |
| 17 | extraction_errors | 0 |
| 18 | malformed_source_problems | 15 |

---

## 3. Destination Routing Breakdown

- **personal_canonical:** 75
- **hardware_state:** 34
- **project_architecture:** 10
- **runbook_procedure:** 6
- **historical_only:** 30
- **transient_noise:** 19
- **sensitive_review:** 0

---

## 4. Safety & Invariant Audit

- **Canonical Claims Before Gemini Ingestion:** 10
- **Canonical Claims After Gemini Ingestion:** 10 (Strictly Preserved: PASS)
- **Total Candidate Claims in Database:** 726 (Baseline 559 + 167 Gemini additions)
- **Total Evidence Rows in Database:** 777 (Baseline 594 + 183 Gemini additions)
- **Candidate Claims with `canonical_effect = 1`:** 0 (Zero automatic promotion: PASS)
- **Candidate Claims with `approved_by` set:** 12 (Human authority strictly preserved: PASS)
- **Replay Idempotency Verification:** 100% PASS across all 20 units
