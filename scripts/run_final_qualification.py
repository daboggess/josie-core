from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Josie")
sys.path.insert(0, str(ROOT))

from mission_manager.dispatcher import MissionManager
from mission_manager.ingress import continue_mission

def main():
    plan = {
        "schema_version": 1,
        "mission_id": "qual-coder-v1-1-final-rerun",
        "title": "Coder Worker v1.1 Final Qualification Re-Run",
        "objective": "Qualify Coder Worker v1.1 by implementing receipt reading and finding helper functions in supervisor/receipts.py.",
        "jobs": [
            {
                "job_id": "job-receipt-helpers",
                "title": "Implement read_receipt and find_receipt helpers in supervisor/receipts.py",
                "department": "coding",
                "objective": (
                    "Inspect supervisor/receipts.py and supervisor/tests/test_receipts.py. "
                    "supervisor/receipts.py currently provides write_receipt(), but lacks standard reading and lookup helpers. "
                    "Implement two public functions in supervisor/receipts.py:\n"
                    "1. `read_receipt(path: Path | str) -> dict`:\n"
                    "   Reads the JSON receipt file at path. Raises FileNotFoundError if path does not exist. "
                    "   Raises ValueError if the file is not a valid JSON dictionary or lacks a non-empty 'schema_version' or 'receipt_id'. "
                    "   Returns the parsed receipt dictionary.\n"
                    "2. `find_receipt(directory: Path | str, job_id: str) -> tuple[dict, Path] | None`:\n"
                    "   Searches directory for files matching '*.json' (ignoring files starting with '.'). "
                    "   Sorts candidates by modification time descending (newest first). "
                    "   Safely reads each JSON file, ignoring corrupted or non-JSON files. "
                    "   Returns (receipt_dict, path) for the first receipt whose 'job_id' matches job_id. "
                    "   Returns None if no matching receipt is found or if directory does not exist.\n"
                    "All 10 unit tests in supervisor/tests/test_receipts.py must pass when running "
                    "python -m unittest supervisor/tests/test_receipts.py. "
                    "Do not modify any file outside supervisor/receipts.py."
                ),
                "first_action": "Inspect supervisor/receipts.py lines 1-30 and supervisor/tests/test_receipts.py.",
                "dependencies": [],
                "workspace": str(ROOT),
                "allowed_changes": ["supervisor/receipts.py"],
                "acceptance": [
                    {
                        "type": "command",
                        "argv": ["python", "-m", "unittest", "supervisor/tests/test_receipts.py"],
                        "expected_exit_code": 0,
                        "timeout_seconds": 60
                    },
                    {"type": "changed_paths"},
                    {"type": "no_unexpected_files"}
                ],
                "timeout": 360
            }
        ]
    }

    missions_dir = ROOT / "data" / "private" / "missions"
    receipts_dir = ROOT / "data" / "private" / "supervisor-local-code"
    orders_dir = ROOT / "data" / "private" / "supervisor-work-orders"

    manager = MissionManager(missions_dir, receipt_directory=receipts_dir, work_order_directory=orders_dir)

    print("=== Step 1: Initializing Mission ===")
    try:
        mission = manager.load(plan["mission_id"])
        print(f"Loaded existing mission {plan['mission_id']} with status {mission['status']}")
    except Exception:
        mission = manager.create(plan)
        print(f"Created mission {plan['mission_id']}")

    print("\n=== Step 2: Executing Mission through Supervisor -> OpenCode -> qwen3:14b ===")
    start_time = time.time()
    outcome = continue_mission(plan["mission_id"], project_root=ROOT)
    elapsed = time.time() - start_time

    print(f"\nExecution finished in {elapsed:.2f}s")
    print(f"Outcome status: {outcome.get('mission_status')}")
    print(f"Stop reason: {outcome.get('stop_reason')}")
    print(f"Latest receipt: {outcome.get('latest_authoritative_receipt')}")
    print(f"Message:\n{outcome.get('assistant_message')}")

if __name__ == "__main__":
    main()
