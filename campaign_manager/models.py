from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    campaign_id: str
    name: str
    work_order_json: str
    state: str
    max_attempts: int
    attempts_used: int
    retry_safe: bool
    idempotency_key: str
    last_supervisor_request_id: str | None
    last_supervisor_receipt_id: str | None
    failure_reason: str | None
    created_at: str
    updated_at: str
    started_at: str | None
    completed_at: str | None
    runner_id: str | None
    claimed_at: str | None
    lease_expires_at: str | None
    current_attempt_id: str | None = None
    current_supervisor_job_id: str | None = None

    @property
    def work_order(self) -> dict[str, Any]:
        return json.loads(self.work_order_json)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        try:
            data["work_order"] = json.loads(self.work_order_json)
        except Exception:
            data["work_order"] = {}
        return data

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> JobRecord:
        keys = row.keys()
        return cls(
            job_id=row["job_id"],
            campaign_id=row["campaign_id"],
            name=row["name"],
            work_order_json=row["work_order_json"],
            state=row["state"],
            max_attempts=int(row["max_attempts"]),
            attempts_used=int(row["attempts_used"]),
            retry_safe=bool(row["retry_safe"]),
            idempotency_key=row["idempotency_key"],
            last_supervisor_request_id=row["last_supervisor_request_id"],
            last_supervisor_receipt_id=row["last_supervisor_receipt_id"],
            failure_reason=row["failure_reason"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            runner_id=row["runner_id"],
            claimed_at=row["claimed_at"],
            lease_expires_at=row["lease_expires_at"],
            current_attempt_id=row["current_attempt_id"] if "current_attempt_id" in keys else None,
            current_supervisor_job_id=row["current_supervisor_job_id"] if "current_supervisor_job_id" in keys else None,
        )


@dataclass(frozen=True)
class CampaignRecord:
    campaign_id: str
    name: str
    created_at: str
    updated_at: str
    status: str
    spec_json: str | None
    runner_id: str | None = None
    lease_claimed_at: str | None = None
    lease_expires_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> CampaignRecord:
        keys = row.keys()
        return cls(
            campaign_id=row["campaign_id"],
            name=row["name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            status=row["status"],
            spec_json=row["spec_json"],
            runner_id=row["runner_id"] if "runner_id" in keys else None,
            lease_claimed_at=row["lease_claimed_at"] if "lease_claimed_at" in keys else None,
            lease_expires_at=row["lease_expires_at"] if "lease_expires_at" in keys else None,
        )


@dataclass(frozen=True)
class AttemptRecord:
    attempt_id: str
    job_id: str
    campaign_id: str
    attempt_number: int
    supervisor_job_id: str
    supervisor_request_id: str | None
    supervisor_receipt_id: str | None
    supervisor_receipt_path: str | None
    status: str
    failure_reason: str | None
    started_at: str
    completed_at: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> AttemptRecord:
        return cls(
            attempt_id=row["attempt_id"],
            job_id=row["job_id"],
            campaign_id=row["campaign_id"],
            attempt_number=int(row["attempt_number"]),
            supervisor_job_id=row["supervisor_job_id"],
            supervisor_request_id=row["supervisor_request_id"],
            supervisor_receipt_id=row["supervisor_receipt_id"],
            supervisor_receipt_path=row["supervisor_receipt_path"],
            status=row["status"],
            failure_reason=row["failure_reason"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True)
class EventRecord:
    event_id: str
    campaign_id: str
    job_id: str
    attempt_number: int | None
    event_type: str
    state_from: str | None
    state_to: str | None
    details_json: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.details_json:
            try:
                data["details"] = json.loads(self.details_json)
            except Exception:
                data["details"] = self.details_json
        else:
            data["details"] = None
        return data

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> EventRecord:
        return cls(
            event_id=row["event_id"],
            campaign_id=row["campaign_id"],
            job_id=row["job_id"],
            attempt_number=row["attempt_number"],
            event_type=row["event_type"],
            state_from=row["state_from"],
            state_to=row["state_to"],
            details_json=row["details_json"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True)
class SupervisorResult:
    final_status: str
    reason: str
    receipt: dict[str, Any] | None = None
    receipt_id: str | None = None
    receipt_path: str | None = None
    error: str | None = None
    worker_prose: str | None = None
