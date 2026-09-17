from __future__ import annotations

import abc
import json
import uuid
from pathlib import Path
from typing import Any, Callable

from .errors import SupervisorIntegrationError
from .models import SupervisorResult


class SupervisorAdapter(abc.ABC):
    """Abstract interface for communicating with the Supervisor boundary."""

    @abc.abstractmethod
    def submit(self, work_order: dict[str, Any]) -> SupervisorResult:
        """Submit a work order to the supervisor and return durable outcome."""
        pass

    @abc.abstractmethod
    def find_receipt(self, receipt_destination: str | Path, job_id: str) -> tuple[dict[str, Any], Path] | None:
        """Query for the most recent receipt matching job_id."""
        pass

    @abc.abstractmethod
    def read_receipt(self, receipt_path: str | Path) -> dict[str, Any]:
        """Read and validate a receipt from disk."""
        pass


class RealSupervisorAdapter(SupervisorAdapter):
    r"""Production adapter invoking D:\Josie\supervisor."""

    def __init__(self) -> None:
        try:
            import sys
            root = Path(r"D:\Josie")
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from supervisor import VERSION
            from supervisor.receipts import find_receipt as _find, read_receipt as _read
            from supervisor.run_job import execute as _execute
            from supervisor.work_order import WorkOrder as _WorkOrder
            self._execute = _execute
            self._read_receipt = _read
            self._find_receipt = _find
            self._work_order_cls = _WorkOrder
            self._supervisor_version = VERSION
        except Exception as exc:
            raise SupervisorIntegrationError(f"Failed to load Supervisor entrypoint: {exc}") from exc

    def verify_connectivity(self) -> dict[str, Any]:
        """Verify imports and entrypoints without launching any processes or mutating state."""
        return {
            "connected": True,
            "supervisor_version": self._supervisor_version,
            "entrypoint": "supervisor.run_job.execute",
            "work_order_validator": "supervisor.work_order.WorkOrder.validate",
            "receipt_reader": "supervisor.receipts.read_receipt",
        }

    def submit(self, work_order: dict[str, Any]) -> SupervisorResult:
        job_id = str(work_order.get("job_id", "unknown"))
        receipt_destination = Path(work_order.get("receipt_destination", r"D:\Josie\data\receipts")).resolve()
        orders_dir = receipt_destination / "work_orders"
        orders_dir.mkdir(parents=True, exist_ok=True)
        
        req_id = uuid.uuid4().hex[:8]
        order_path = orders_dir / f"{job_id}_{req_id}.json"
        order_path.write_text(json.dumps(work_order, indent=2), encoding="utf-8")

        try:
            receipt, receipt_path = self._execute(order_path)
            status = receipt.get("final_status", "UNKNOWN")
            reason = receipt.get("reason", "")
            receipt_id = receipt.get("receipt_id") or (receipt_path.stem if receipt_path else None)
            return SupervisorResult(
                final_status=status,
                reason=reason,
                receipt=receipt,
                receipt_id=receipt_id,
                receipt_path=str(receipt_path) if receipt_path else None,
                error=receipt.get("error"),
            )
        except Exception as exc:
            raise SupervisorIntegrationError(f"Supervisor execution failed: {exc}") from exc

    def find_receipt(self, receipt_destination: str | Path, job_id: str) -> tuple[dict[str, Any], Path] | None:
        try:
            return self._find_receipt(receipt_destination, job_id)
        except Exception:
            return None

    def read_receipt(self, receipt_path: str | Path) -> dict[str, Any]:
        return self._read_receipt(receipt_path)


class FakeSupervisorAdapter(SupervisorAdapter):
    """Deterministic in-memory/file adapter for testing and verification."""

    def __init__(self) -> None:
        self.canned_results: dict[str, SupervisorResult | Exception | Callable[[dict[str, Any]], SupervisorResult]] = {}
        self.call_history: list[dict[str, Any]] = []
        self.stored_receipts: dict[str, dict[str, Any]] = {}
        self.disk_receipt_paths: dict[str, Path] = {}

    def set_result(self, job_id: str, result: SupervisorResult | Exception | Callable[[dict[str, Any]], SupervisorResult]) -> None:
        self.canned_results[job_id] = result

    def store_receipt(self, job_id: str, receipt: dict[str, Any], path: Path | None = None) -> None:
        self.stored_receipts[job_id] = receipt
        if path:
            self.disk_receipt_paths[job_id] = path

    def submit(self, work_order: dict[str, Any]) -> SupervisorResult:
        self.call_history.append(dict(work_order))
        job_id = work_order.get("job_id", "")
        base_id = job_id.split("--a")[0]
        
        canned = None
        if job_id in self.canned_results:
            canned = self.canned_results[job_id]
        elif base_id in self.canned_results:
            canned = self.canned_results[base_id]

        if canned is not None:
            if isinstance(canned, Exception):
                raise canned
            elif callable(canned):
                res = canned(work_order)
            else:
                res = canned
            if isinstance(res.receipt, dict):
                if res.receipt.get("job_id") == base_id:
                    res.receipt["job_id"] = job_id
                if res.receipt_id:
                    self.stored_receipts[job_id] = res.receipt
            return res

        # Default PASS response
        rid = str(uuid.uuid4())
        receipt = {
            "schema_version": "1",
            "receipt_id": rid,
            "job_id": job_id,
            "final_status": "PASS",
            "reason": "PASS",
        }
        self.stored_receipts[job_id] = receipt
        return SupervisorResult(
            final_status="PASS",
            reason="PASS",
            receipt=receipt,
            receipt_id=rid,
            receipt_path=f"/fake/receipts/{rid}.json",
        )

    def find_receipt(self, receipt_destination: str | Path, job_id: str) -> tuple[dict[str, Any], Path] | None:
        # First check disk if real files were written
        dest = Path(receipt_destination)
        if dest.is_dir():
            for f in dest.glob("*.json"):
                if not f.name.startswith("."):
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        if data.get("job_id") == job_id:
                            return data, f
                    except Exception:
                        pass
        # Then check in-memory store
        if job_id in self.stored_receipts:
            rcpt = self.stored_receipts[job_id]
            path = self.disk_receipt_paths.get(job_id, dest / f"{rcpt.get('receipt_id', 'unknown')}.json")
            return rcpt, path
        return None

    def read_receipt(self, receipt_path: str | Path) -> dict[str, Any]:
        p = Path(receipt_path)
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
        for rcpt in self.stored_receipts.values():
            if rcpt.get("receipt_id") in p.name:
                return rcpt
        raise FileNotFoundError(f"Receipt not found: {receipt_path}")
