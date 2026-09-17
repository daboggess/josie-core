# BUILD RECEIPT: Mission Manager → Campaign Manager Bridge v0.1

- **Build Target:** Mission Manager → Campaign Manager Bridge v0.1
- **Version:** 0.1.1
- **Status:** **PASS**
- **Date / Timestamp:** 2026-09-13T20:18:00Z
- **Qualified Authority Baseline:**
  - Supervisor: `D:\Josie\supervisor` (v0.2.1) — 85/85 tests PASS
  - Campaign Manager: `D:\Josie\campaign_manager` (v0.1.1) — 43/43 tests PASS
  - Mission Manager Bridge: `D:\Josie\mission_manager\campaign_bridge.py` — 25/25 tests PASS
  - Existing Mission Frontdoor: `D:\Josie\tests\test_mission_*.py` — 38/38 tests PASS
  - Database: `D:\Josie\data\josie.db` (14,876,672 bytes, UNTOUCHED)

---

## 1. Architectural Boundary & Responsibilities

The bridge provides an adapter and orchestration boundary connecting high-level Mission Plans to Campaign Manager v0.1.1 without bypassing the Supervisor authority boundary:

`Josie / Mission Manager` → `Mission Plan` → `Mission → Campaign Bridge` → `Campaign Manager v0.1.1` → `Supervisor` → `bounded worker` → `machine acceptance` → `durable Supervisor receipt` → `Campaign Manager state` → `Mission-level status / receipt`.

Key invariant guarantees:
1. **Bridge is an adapter, not a worker:** The bridge does NOT execute tools directly and does not launch worker processes.
2. **Authority preservation:** Allowed changed paths, acceptance checks, timeouts, and forbidden paths are strictly passed through without widening.
3. **Approval gating:** Jobs requiring approval map to `JobState.WAITING_APPROVAL` and cause Mission state to reflect `WAITING_APPROVAL`.
4. **Idempotent submission:** Submitting the same mission plan twice safely returns the existing campaign without creating duplicate records or jobs.
5. **Durable derivation:** Mission state is strictly derived from Campaign Manager and Supervisor durable machine evidence. Prose from workers cannot cause PASS.

---

## 2. Test Verification Matrix

| Test Suite | Path | Tests Run | Result | Duration |
|------------|------|-----------|--------|----------|
| Bridge Unit Tests (22 required + 3 extended) | `D:\Josie\mission_manager\tests\test_campaign_bridge.py` | 25 | **PASS** | 1.32s |
| Mission Manager Legacy Tests | `D:\Josie\tests\test_mission_*.py` | 38 | **PASS** | 1.11s |
| Campaign Manager Tests | `D:\Josie\campaign_manager\tests\test_*.py` | 43 | **PASS** | 6.06s |
| Supervisor Regression Tests | `D:\Josie\supervisor\tests\test_*.py` | 85 | **PASS** | 9.94s |

---

## 3. Real Field Qualification Summary

A 3-job Mission (`bridge-qual-001`) was submitted through `CampaignBridge` and executed against the real Campaign Manager, Supervisor v0.2.1, and local OpenCode 1.18.23 worker:

- **Mission ID:** `bridge-qual-001`
- **Campaign ID:** `mission-bridge-qual-001`
- **Elapsed Time:** 81.42s
- **Job A (`bridge-qual-job-a`):** Independent artifact creation (`artifact_a.json`) -> **PASS** (Attempt 1, receipt: `20ed2ee5-8947-4d76-b91c-3b46dff55029`)
- **Job B (`bridge-qual-job-b`):** Chained artifact creation (`artifact_b.json`, depends on A) -> **PASS** (Attempt 1, receipt: `318606a4-6517-44a4-bb43-e1eb20f29329`)
- **Job C (`bridge-qual-job-c`):** Independent artifact creation (`artifact_c.json`) -> **PASS** (Attempt 1, receipt: `577bdc19-2dab-41cc-b325-e35037e18441`)
- **Durable Mission Receipt:** `D:\Josie\data\mission_receipts\bridge-qual-001.json`
- **Final Verdict:** **PASS**

---

## 4. Scope & File Integrity

- **Files Created:**
  - `D:\Josie\mission_manager\campaign_bridge.py`
  - `D:\Josie\mission_manager\db.py`
  - `D:\Josie\mission_manager\tests\__init__.py`
  - `D:\Josie\mission_manager\tests\test_campaign_bridge.py`
  - `D:\Josie\mission_manager\BUILD_RECEIPT.md`
  - `D:\Josie\mission_manager\build_receipt.json`
- **Files Modified:**
  - `D:\Josie\mission_manager\__init__.py` (exported bridge symbols)
  - `D:\Josie\mission_manager\models.py` (added bridge states to MISSION_STATES)
  - `D:\Josie\mission_manager\cli.py` (added submit and status commands)
- **Files Untouched:**
  - `D:\Josie\campaign_manager\**` (0 changes)
  - `D:\Josie\supervisor\**` (0 changes)
  - `D:\Josie\data\josie.db` (14,876,672 bytes, 0 changes)
