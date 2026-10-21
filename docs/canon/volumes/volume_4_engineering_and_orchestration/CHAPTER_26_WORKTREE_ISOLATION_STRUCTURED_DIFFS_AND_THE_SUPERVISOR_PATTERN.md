# CHAPTER 26: Worktree Isolation, Structured Diffs, and the Supervisor Pattern

> *"A developer does not test experimental hydraulics on the main assembly line. You build a test bench, clamp the valve down, run the pressure test to failure, and inspect the seals. Only after the bench confirms integrity does the valve go into the tractor."*  
> — Dustin, Architectural Directive on Supervisor Verification (`CON-0007`)

---

## § 26.1 Git Worktrees: The Physical Test Bench

To ensure that the Dedicated Local Coder cannot destabilize active operations, all coding execution occurs inside isolated **Git Worktrees**.

A git worktree allows multiple working directories to be linked to a single repository storage database. While Josie’s production daemon executes against the `main` or active deployment branch in `D:\Josie`, the supervisor harness spawns an ephemeral worktree in an isolated path:
`D:\josie-worktrees\task-eng-2026-0812`

```
  [ PRIMARY REPOSITORY: D:\Josie ]
               |
  (Branch: feature/summit-status-summary)
               |
  +-------------------------------------------------------------+
  | Supervisor Spawns Ephemeral Worktree                         |
  | Target: D:\josie-worktrees	ask-eng-2026-0812               |
  |                                                             |
  |  1. Apply Local Coder Unified Diff                          |
  |  2. Run 'black --check' & 'ruff check'                      |
  |  3. Run 'mypy --strict'                                     |
  |  4. Run 'pytest -v tests/target_suite.py'                   |
  |  5. Collect Execution Receipts & Test Artifacts             |
  +-------------------------------------------------------------+
               |
  [ PASS: Forward to Dustin's Decision Queue ]
  [ FAIL: Prune Worktree & Abort Task ]
```

The coding model operates exclusively within this sandboxed directory. It has no write handles to the primary working copy. If the model generates destructive code, unlinks files, or enters an infinite loop, the primary deployment remains completely untouched.

---

## § 26.2 The Three-Tier Supervisor Verification Pipeline

Once the coder emits a unified diff and the diff applies cleanly to the worktree, the **Supervisor Harness** executes a non-negotiable three-tier verification pipeline:

### 1. Static Syntax & Style Gate
The supervisor executes deterministic linters:
- `ruff check .`: Catches unused imports, undefined variables, and common Python anti-patterns.
- `mypy --strict [target_file]`: Verifies complete type integrity, ensuring no untyped objects or invalid type conversions were introduced.

### 2. Behavioral Unit Test Gate
The supervisor executes the project’s pytest suite against the modified worktree:
- Validates that new tests written for the issue pass.
- Validates that zero existing regression tests fail.
- Confirms test execution time remains within acceptable bounds.

### 3. Receipt Generation & Worktree Teardown
If all gates pass:
- The supervisor computes the SHA-256 hash of the unified diff.
- Generates a signed execution receipt.
- Files a structured proposal in `decision_queue_v2` for Dustin’s review.
- Teardown of the ephemeral worktree occurs cleanly: `git worktree remove --force`.

---

## § 26.3 Zero Hallucination in Version Control

By decoupling *generation* from *acceptance*, Project Josie achieves zero hallucination in its version control history. 

A human developer reviewing a pull request does not need to wade through twenty intermediate commits of AI trial-and-error. The human sees only one clean, verified, syntactically pure unified diff, accompanied by an immutable cryptographic receipt proving that all automated test gates passed.

The machine proposes; the supervisor verifies; the human ratifies.
