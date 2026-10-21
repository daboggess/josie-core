# CHAPTER 20: The Local Model Inventory and Role Specialization

> *"A model is not an identity; it is an employee assigned to a desk. The desk has a job description, a set of tools, and a strict supervisor. When the employee changes, the company remains."*  
> — Dustin, Architectural Note on Model Specialization

---

## § 20.1 The Quad-State Model Inventory Taxonomy

A major failure in amateur AI documentation is conflating *proposed* or *historical* models with *active* runtime models. A documentation audit conducted in October 2026 revealed that early drafts of the Core Canon mistakenly listed speculative models as active components.

To maintain strict epistemic precision, Josie classifies every AI model into one of four verified taxonomy states:

```
+-----------------------------------------------------------------------------+
|                          MODEL TAXONOMY STATES                              |
+------------------------------------+----------------------------------------+
| 1. INSTALLED & AVAILABLE           | Present in local storage; ready to load|
| 2. ACTIVELY ASSIGNED               | Bound to an active operational tier    |
| 3. EVALUATION / CANDIDATE          | Undergoing benchmark testing; unassigned|
| 4. HISTORICAL / RETIRED            | Formerly used; permanently superseded  |
+------------------------------------+----------------------------------------+
```

---

## § 20.2 The Active Local Inventory

As verified through local runtime inspection and Ollama manifest audits, the active local model inventory within the 12GB envelope comprises:

| Model Identifier | Parameter Count | Quantization | Size on Disk | Assigned Operational Role |
| :--- | :--- | :--- | :--- | :--- |
| **`qwen2.5:7b-instruct`** | 7.6 Billion | Q5_K_M | 5.4 GB | **Resident Local Generalist (Tier 2)** |
| **`qwen2.5-coder:14b`** | 14.7 Billion | Q4_K_M | 9.0 GB | **Dedicated Local Coder (Tier 3)** |
| **`llama3.2:3b`** | 3.2 Billion | Q8_0 | 3.4 GB | **Fast Triage & Gatekeeper (Tier 5 / Ingest)** |
| **`nomic-embed-text`** | 137 Million | FP16 | 274 MB | **Local Semantic Anchor / Verification** |

### Role Breakdown:
1. **The Resident Generalist (`qwen2.5:7b`):** Fast, articulate, and exceptionally obedient to markdown system constraints. Handles day-to-day conversation, task planning, decision queue formatting, and user interaction.
2. **The Dedicated Coder (`qwen2.5-coder:14b`):** High-precision code generation model. Used exclusively within isolated worktrees to generate unified diffs against specific issue descriptions.
3. **The Triage Specialist (`llama3.2:3b`):** Micro-footprint model. Evaluates incoming email notifications, deals, and logs with millisecond latency without requiring significant VRAM.

---

## § 20.3 Evaluated and Historical Models

Josie’s intellectual heritage includes numerous models that were tested, benchmarked, and subsequently retired:
- **`mistral:7b-instruct-v0.2` (Historical):** The early workhorse of the Hydra and D-Bot prototypes. Highly capable in late 2023, but superseded by Qwen 2.5’s superior structured JSON output and instruction adherence.
- **`deepseek-coder:6.7b` (Historical):** Predecessor coding engine. Replaced by Qwen 2.5 Coder 14B once Q4_K_M quantization allowed 14B execution within the 12GB budget.
- **`phi-3 / phi-4` (Evaluation):** Tested for high-density reasoning, but exhibited excessive instruction-tuning quirks when parsing complex multi-tier system prompts.
- **`gemma-2:9b` (Evaluation):** Tested extensively. Produced excellent prose, but high KV cache memory overhead made 16K context window operations unstable under the 12GB limit.
