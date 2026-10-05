# Cross-Source Corroborated Candidate Claims

This document catalogs candidate claims independently asserted and verified by historical evidence from **BOTH ChatGPT and Google Gemini**.

Cross-source corroboration significantly elevates evidentiary weight by proving that a fact or preference was asserted across independent platforms, different LLM contexts, and multiple distinct calendar dates.

---

## 1. Exact Literal Corroborations (Identical Claim ID)

The following 5 claims generated the exact same canonical claim ID from both corpora:

### 1. `claim:candidate:person:dustin:current_state:9c9c9d886c9d694d`
- **Subject:** `person:dustin`
- **Predicate:** `current_state`
- **Value:** `owns i7-7700 CPU and 32GB RAM`
- **Category:** `hardware` | **Durability:** `current_state`
- **Evidence Cross-Reference:**
  - `[GOOGLE_GEMINI]` Message 4540 (2026-08-03): *"We upgraded to i7 7700 and 32g ram"*
  - `[OPENAI_CHATGPT]` Message 21107 (2026-08-25): *"Okay, what's the intelligence driving this? Like I know we said OpenWeb UI ... i7 7700 and 32GB RAM"*

---

### 2. `claim:candidate:person:dustin:does_not_own:008400c4938cb1b5`
- **Subject:** `person:dustin`
- **Predicate:** `does_not_own`
- **Value:** `RTX 3060`
- **Category:** `hardware` | **Durability:** `current_state`
- **Evidence Cross-Reference:**
  - `[GOOGLE_GEMINI]` Message 5097 (2026-08-25): *"well that 3060 sold as i was chatting with the guy, wasnt meant to be"*
  - `[OPENAI_CHATGPT]` Message 10577 (2025-12-11): *"No existing 3060 please save to memory"*

---

### 3. `claim:candidate:person:dustin:has_identity:22a9cd4d8ea1f55c`
- **Subject:** `person:dustin`
- **Predicate:** `has_identity`
- **Value:** `Dustin`
- **Category:** `identity` | **Durability:** `durable`
- **Evidence Cross-Reference:**
  - `[GOOGLE_GEMINI]` Message 731 (2026-01-20): *"Okay, I noticed you said Claire. You don't need to address yourself as Claire... Call me Dustin"*
  - `[OPENAI_CHATGPT]` Message 9998 (2025-12-01): *"Well, first off, please quit saying Soph. Like, I still acknowledge I call you that, but you call me Dustin."*

---

### 4. `claim:candidate:person:dustin:prefers_local_first_desktop_ai_setup:7cd4ba7ee9db062d`
- **Subject:** `person:dustin`
- **Predicate:** `prefers_local_first_desktop_ai_setup`
- **Value:** `to minimize cloud dependency and subscription usage`
- **Category:** `preference` | **Durability:** `preference`
- **Evidence Cross-Reference:**
  - `[GOOGLE_GEMINI]` Message 5095 (2026-08-25): *"Audit the existing Josie... local first"*
  - `[OPENAI_CHATGPT]` Message 21046 (2026-08-25): *"Yeah again this is another reason I want a local model with more memory because I don't want to rely on cloud"*

---

### 5. `claim:candidate:person:dustin:prefers_model_access_without_subscription_burn:5ffaa93fd9cba477`
- **Subject:** `person:dustin`
- **Predicate:** `prefers_model_access_without_subscription_burn`
- **Value:** `to maintain existing subscription limits`
- **Category:** `preference` | **Durability:** `preference`
- **Evidence Cross-Reference:**
  - `[GOOGLE_GEMINI]` Message 5097 (2026-08-25): *"sent to sophie well that 3060 sold as i was chatting with the guy, wasnt meant to be... need local access"*
  - `[OPENAI_CHATGPT]` Message 21070 (2026-08-25): *"And again, I want to give it as much access to you and Gemini, Bernie as possible without burning through limits."*

---

## 2. Key Semantic Corroborations & Refinements

### A. Storage Architecture Corroboration
- **ChatGPT Candidate:** `claim:candidate:person:dustin:owns:42c75990...` ("owns 24TB HDDs and 4TB NVMe SSDs")
- **Gemini Candidate:** `claim:candidate:person:dustin:owns:9824f42ffde63cdf` ("two 24TB Seagate Exostraves and 24TB NVMe drives")
  - Gemini Message 152: *"I currently have two twenty four TB Seagate Exostraves and 24 TB NVMe drives that I could use for this build."*
  - **Verdict:** Fully corroborated; Gemini refines drive brand as Seagate Exos.

### B. Business Operations & Vape Shop Refinement
- **ChatGPT Candidate:** `claim:candidate:person:dustin:runs:vape_shop` ("runs Full Steam Vapor for 11 years")
- **Gemini Candidates:**
  - `claim:candidate:322:suggest:7218d731ae6ccfd0`: *"We do offer 5% cash back loyalty rewards."* (Msg 322)
  - `claim:candidate:324:suggest:57eedd2d4a4a8f8d`: *"and 10% off for military and first responders."* (Msg 324)
  - **Verdict:** Operational policy details refine the business profile.

### C. Church & AV Production Corroboration
- **ChatGPT Candidate:** `claim:candidate:person:dustin:attending_and_serving_at_river_ridge_tv`
- **Gemini Candidate:** `claim:candidate:person:dustin:has_production_role:river_ridge`
  - **Verdict:** Corroborated volunteer activity in AV production at River Ridge.
