from __future__ import annotations

from .dispatcher import MissionManager, _refresh
from .models import now
from .receipts import read_authoritative_receipt


FAILED_RECEIPT_ID = "f6b2755f-940a-4a1a-818b-f51fa188e017"
PYTHON = r"D:\Josie\.venv\Scripts\python.exe"
ROOT = r"D:\Josie"
JOB_1A_FIRST_ACTION = r"Inspect whether dbot\contracts.py exists, then create/update it."
JOB_1A_OBJECTIVE = """Create only dbot/contracts.py with minimal Python standard-library data structures for Seal, Ring, and Scroll.

Seal fields:
- principal_id
- issuer
- created_at
- provenance

Ring fields:
- allowed_paths
- allowed_tools
- allowed_models
- allowed_providers
- network_allowed
- credential_access_allowed
- package_install_allowed
- software_install_allowed
- side_effects_allowed
- spending_limit
- communications_allowed
- deletion_allowed
- approval_required
- expires_at

Scroll fields:
- job_id
- objective
- context_refs
- acceptance_criteria
- constraints
- authorized_resources
- prohibited_actions
- expected_outputs
- verification_requirements
- rollback_requirements
- receipt_requirements
- expires_at

Implementation constraints:
- Python standard library only
- dataclasses or similarly small structures
- JSON-compatible to_dict() or equivalent
- no cryptography
- no secrets
- no validation beyond normal constructor requirements
- no README
- no examples
- no tests in this job"""


def _job(job_id: str, title: str, objective: str, dependencies: list[str],
         allowed: list[str], acceptance: list[dict], *, first_action: str | None = None) -> dict:
    return {
        "job_id": job_id, "title": title, "department": "coding", "objective": objective,
        "dependencies": dependencies, "status": "WAITING", "workspace": ROOT,
        "allowed_changes": allowed, "acceptance": acceptance, "timeout": 120,
        "attempts": 0, "receipt_ref": None, "result_reason": None, "required": True,
        "requires_modification": True, "independent_responsibilities": [], "dispatch_ids": [],
        "first_action": first_action,
    }


def apply_authorized_decomposition(manager: MissionManager, mission_id: str = "dbot-seed-v0") -> tuple[dict, bool]:
    mission = manager.load(mission_id)
    ids = {job["job_id"] for job in mission["jobs"]}
    decomposition = {"job-1a-contract-structures", "job-1b-contract-tests", "job-1c-package-exports"}
    if decomposition <= ids:
        return mission, False
    if ids & decomposition:
        raise ValueError("D-bot decomposition is partially persisted")
    old = next((job for job in mission["jobs"] if job["job_id"] == "job-1-contracts"), None)
    if old is None or old.get("result_reason") != "FAIL_TIMEOUT" or old.get("receipt_ref") is None:
        raise ValueError("authoritative failed D-bot job is unavailable")
    evidence = read_authoritative_receipt(old["receipt_ref"], expected_job_id=old["dispatch_ids"][-1])
    if (evidence["receipt_id"] != FAILED_RECEIPT_ID or evidence["reason"] != "FAIL_TIMEOUT"
            or evidence.get("files_changed") or abs(float(evidence.get("elapsed_seconds") or 0) - 120.187) > 0.01):
        raise ValueError("failed D-bot receipt does not match authorized adaptation evidence")

    old["status"] = "SKIPPED"
    old["required"] = False
    old["result_reason"] = "SUPERSEDED_BY_DECOMPOSITION"
    old["superseded_by"] = sorted(decomposition)
    job_1a = _job(
        "job-1a-contract-structures", "Create D-bot contract structures",
        JOB_1A_OBJECTIVE,
        [], ["dbot/contracts.py"],
        [{"type": "command", "argv": [PYTHON, "-m", "py_compile", "dbot/contracts.py"], "expected_exit_code": 0, "timeout_seconds": 60},
         {"type": "file_exists", "path": "dbot/contracts.py"}, {"type": "changed_paths"}, {"type": "no_unexpected_files"}],
        first_action=JOB_1A_FIRST_ACTION,
    )
    job_1b = _job(
        "job-1b-contract-tests", "Test D-bot contract structures",
        "Add deterministic standard-library tests in tests/test_dbot_contracts.py for the existing Seal, Ring, and Scroll structures, including construction, JSON-compatible serialization round trips, and rejection of structurally invalid values. Repair dbot/contracts.py only if required for these contract tests. Do not add package exports, documentation, or authority validation.",
        [job_1a["job_id"]], ["tests/test_dbot_contracts.py", "dbot/contracts.py"],
        [{"type": "command", "argv": [PYTHON, "-m", "unittest", "-v", "tests.test_dbot_contracts"], "expected_exit_code": 0, "timeout_seconds": 60},
         {"type": "file_exists", "path": "tests/test_dbot_contracts.py"}, {"type": "changed_paths"}, {"type": "no_unexpected_files"}],
    )
    job_1c = _job(
        "job-1c-package-exports", "Expose D-bot contracts package",
        "Create dbot/__init__.py exporting Seal, Ring, and Scroll from the existing contracts module. Change no other file.",
        [job_1b["job_id"]], ["dbot/__init__.py"],
        [{"type": "command", "argv": [PYTHON, "-c", "from dbot import Seal, Ring, Scroll; print('DBOT_CONTRACTS_OK')"], "expected_exit_code": 0, "timeout_seconds": 60},
         {"type": "file_exists", "path": "dbot/__init__.py"}, {"type": "changed_paths"}, {"type": "no_unexpected_files"}],
    )
    remaining = {job["job_id"]: job for job in mission["jobs"] if job["job_id"] != old["job_id"]}
    job_2 = remaining["job-2-authority"]
    job_2.update(status="WAITING", dependencies=[job_1c["job_id"]], workspace=ROOT,
                 allowed_changes=["dbot/authority.py", "tests/test_dbot_authority.py"], attempts=0,
                 receipt_ref=None, result_reason=None, dispatch_ids=[])
    job_2["acceptance"] = [
        {"type": "command", "argv": [PYTHON, "-m", "unittest", "-v", "tests.test_dbot_authority"], "expected_exit_code": 0, "timeout_seconds": 60},
        {"type": "file_exists", "path": "dbot/authority.py"}, {"type": "file_exists", "path": "tests/test_dbot_authority.py"},
        {"type": "changed_paths"}, {"type": "no_unexpected_files"}]
    job_3 = remaining["job-3-docs"]
    job_3.update(status="WAITING", dependencies=[job_2["job_id"]], workspace=ROOT,
                 allowed_changes=["dbot/README.md", "dbot/examples/example_authority.json"], attempts=0,
                 receipt_ref=None, result_reason=None, dispatch_ids=[])
    job_3["acceptance"] = [
        {"type": "file_exists", "path": "dbot/README.md"}, {"type": "file_exists", "path": "dbot/examples/example_authority.json"},
        {"type": "command", "argv": [PYTHON, "-c", "import json,pathlib; p=pathlib.Path('dbot/examples/example_authority.json'); d=json.loads(p.read_text(encoding='utf-8')); assert d and 'secret' not in p.read_text(encoding='utf-8').lower()"], "expected_exit_code": 0, "timeout_seconds": 30},
        {"type": "changed_paths"}, {"type": "no_unexpected_files"}]
    job_4 = remaining["job-4-verification"]
    job_4.update(status="WAITING", dependencies=[job_3["job_id"]], workspace=ROOT,
                 allowed_changes=["dbot/VERIFICATION.md"], attempts=0, receipt_ref=None,
                 result_reason=None, dispatch_ids=[])
    job_4["acceptance"] = [
        {"type": "command", "argv": [PYTHON, "-m", "unittest", "-v", "tests.test_dbot_contracts", "tests.test_dbot_authority"], "expected_exit_code": 0, "timeout_seconds": 60},
        {"type": "file_exists", "path": "dbot/VERIFICATION.md"}, {"type": "changed_paths"}, {"type": "no_unexpected_files"}]
    mission["jobs"] = [old, job_1a, job_1b, job_1c, job_2, job_3, job_4]
    mission["dependency_graph"] = {job["job_id"]: job["dependencies"] for job in mission["jobs"]}
    mission["status"] = "PLANNED"
    mission["current_job"] = job_1a["job_id"]
    mission["updated_at"] = now()
    mission.setdefault("applied_adaptations", []).append({
        "applied_at": mission["updated_at"], "type": "DECOMPOSE_JOB", "authorized": True,
        "source_job_id": old["job_id"], "receipt_id": FAILED_RECEIPT_ID,
        "replacement_job_ids": [job_1a["job_id"], job_1b["job_id"], job_1c["job_id"]],
    })
    _refresh(mission)
    manager.store.save(mission)
    manager.store.append_event(mission_id, {"event": "AUTHORIZED_DECOMPOSITION_APPLIED", "at": mission["updated_at"],
        "source_job_id": old["job_id"], "receipt_id": FAILED_RECEIPT_ID,
        "replacement_job_ids": [job_1a["job_id"], job_1b["job_id"], job_1c["job_id"]]})
    return manager.load(mission_id), True
