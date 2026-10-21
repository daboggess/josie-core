# CHAPTER 25: The Supervised Local Coding Worker

> *"The coder is a craftsman in a secure booth. It receives an exact blueprint through the slot, crafts the requested component with meticulous precision, and passes the part back through the slot for inspection. It does not wander around the factory floor."*  
> — Coder Worker Operational Manual (`DEC-0014`)

---

## § 25.1 The Role of Tier 3: Dedicated Local Coder

In Josie’s Five-Tier Operating Topology, **Tier 3** is occupied by the **Dedicated Local Coder**. Currently fulfilled by **`qwen2.5-coder:14b`** (running under Q4_K_M quantization within the 12GB VRAM ceiling), the coder represents an industrial specialist.

The coder worker is deliberately isolated from general conversation, emotional nuances, high-level task planning, and external web interactions. It does not chat; it does not reason about household logistics; it does not evaluate deals. It receives structured engineering work orders and produces validated code modifications.

---

## § 25.2 The Task Specification Contract

A coding worker is never invoked with vague, open-ended prompts like *"Improve the performance of our database queries."* Such prompts invite hallucination and scope creep.

Under **Decision `DEC-0014`**, every task dispatched to Tier 3 must adhere to the **Task Specification Contract**:

```yaml
task_specification:
  task_id: "TASK-ENG-2026-0812"
  target_file: "josie/memory/priming.py"
  start_line: 142
  end_line: 188
  objective: "Refactor JSON serialization to enforce sort_keys=True and UTF-8 bytes output"
  invariants:
    - "Do not introduce external dependencies"
    - "Preserve existing function signature"
    - "Ensure exact match with acceptance test C1-06"
  context_snippets:
    - "tests/test_priming_dual_hash.py"
```

By providing exact line ranges, file targets, and explicit invariants, the search space for the model is constrained. The model’s entire attention capacity is concentrated upon solving the exact algorithmic problem specified.

---

## § 25.3 Structured Diff-Only Generation

The output format of the Dedicated Local Coder is strictly governed. The model is forbidden from returning explanatory conversational prose, apologies, or markdown conversational filler (*"Sure! Here is the updated code for you..."*).

It must return a raw, syntactically valid unified diff:

```diff
--- a/josie/memory/priming.py
+++ b/josie/memory/priming.py
@@ -145,5 +145,6 @@ def canonical_serialize(data: Any) -> bytes:
-    return json.dumps(data).encode()
+    return json.dumps(
+        data,
+        sort_keys=True,
+        ensure_ascii=False,
+        separators=(',', ':')
+    ).encode('utf-8')
```

If the model outputs extraneous text outside the diff block, the worker wrapper automatically strips it. If the diff fails `git apply --check`, the task is immediately marked `FAILED` with an eviction notice sent to the mission manager.

---

## § 25.4 Benchmark Receipts and Empirical Performance

The assignment of `qwen2.5-coder:14b` to Tier 3 was not an ideological choice; it was grounded in rigorous empirical benchmarking on the Advantech rig.

In benchmark run `ec44774e`, Qwen 2.5 Coder 14B was evaluated against 50 targeted refactoring tasks across Josie's Python codebase:
- **Syntax Validity:** 100% (50/50 valid AST parsable outputs)
- **Diff Applicability:** 96% (48/50 diffs applied cleanly via `git apply`)
- **Regression Pass Rate:** 92% (46/50 passed all existing unit tests on first pass)
- **Execution Speed:** 24.8 tokens per second on the 12GB GPU
- **VRAM Footprint:** 9.1 GB resident, comfortably below the 11.5 GB danger threshold.

This benchmark confirmed that local, open-weights models operating within a 12GB envelope possess all the precision required for production engineering, provided they are bound to strict supervisory contracts.
