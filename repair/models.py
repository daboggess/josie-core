from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class InvalidRepairTicket(ValueError):
    pass


@dataclass(frozen=True)
class RepairTicket:
    repair_id: str
    department: str
    failed_job_id: str
    receipt_refs: tuple[str, ...]
    expected_state: dict[str, Any]
    observed_failure_class: str
    authorized_recovery_actions: tuple[str, ...]
    acceptance: tuple[dict[str, Any], ...]
    attempt_budget: int

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RepairTicket":
        required = {
            "repair_id", "department", "failed_job_id", "receipt_refs",
            "expected_state", "observed_failure_class",
            "authorized_recovery_actions", "acceptance", "attempt_budget",
        }
        missing = sorted(required - value.keys())
        if missing:
            raise InvalidRepairTicket(f"missing fields: {', '.join(missing)}")
        if value["department"] != "coding":
            raise InvalidRepairTicket("Repair Worker v0 supports only department=coding")
        if value["observed_failure_class"] != "coding_worker_unresponsive":
            raise InvalidRepairTicket("Repair Worker v0 supports only coding_worker_unresponsive")
        if not isinstance(value["attempt_budget"], int) or value["attempt_budget"] not in (1, 2):
            raise InvalidRepairTicket("attempt_budget must be 1 or 2")
        if not isinstance(value["expected_state"], dict):
            raise InvalidRepairTicket("expected_state must be an object")
        if not isinstance(value["acceptance"], list) or not value["acceptance"]:
            raise InvalidRepairTicket("acceptance must be a non-empty list")
        return cls(
            repair_id=str(value["repair_id"]),
            department=value["department"],
            failed_job_id=str(value["failed_job_id"]),
            receipt_refs=tuple(map(str, value["receipt_refs"])),
            expected_state=dict(value["expected_state"]),
            observed_failure_class=value["observed_failure_class"],
            authorized_recovery_actions=tuple(map(str, value["authorized_recovery_actions"])),
            acceptance=tuple(dict(item) for item in value["acceptance"]),
            attempt_budget=value["attempt_budget"],
        )


@dataclass
class RepairReceipt:
    repair_id: str
    failed_job_id: str
    playbook: str = "coding_worker_unresponsive"
    final_status: str = "BLOCKED"
    reason: str = "NOT_RUN"
    expected_state: dict[str, Any] = field(default_factory=dict)
    actual_before: dict[str, Any] = field(default_factory=dict)
    material_differences: list[str] = field(default_factory=list)
    recovery_actions: list[dict[str, Any]] = field(default_factory=list)
    attempts_used: int = 0
    actual_after: dict[str, Any] = field(default_factory=dict)
    supervisor_receipt_ref: str | None = None
    externally_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
