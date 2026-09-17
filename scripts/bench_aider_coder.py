"""Phase C: Sovereign Coder Qualification under Aider Harness.
Evaluates:
  Model: qwen2.5-coder:14b (held constant from Phase B)
  Harness: Aider 0.86.2 (Challenger harness)
  Format: diff (unified SEARCH/REPLACE diff editing)
  Runtime: Local Ollama only (zero cloud, zero paid API, zero internet)
  Task: Implement read_receipt and find_receipt in supervisor/receipts.py
"""
from __future__ import annotations

import difflib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import build_opener, ProxyHandler, Request

ROOT = Path(r"D:\Josie")
RECEIPTS_FILE = ROOT / "supervisor" / "receipts.py"
BASELINE_RECEIPTS_CONTENT = """from __future__ import annotations

import json
import os
import uuid
from pathlib import Path


def write_receipt(directory: Path, receipt: dict, receipt_id: str | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    rid = receipt_id or str(uuid.uuid4())
    target = directory / f"{rid}.json"
    if target.exists():
        raise FileExistsError(f"receipt already exists: {target}")
    temporary = directory / f".{rid}.{uuid.uuid4().hex}.tmp"
    payload = dict(receipt, receipt_id=rid)
    try:
        with temporary.open("x", encoding="utf-8", newline="\\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\\n")
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            raise FileExistsError(f"receipt already exists: {target}")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target
"""

OLLAMA_URL = "http://127.0.0.1:11434"
AIDER_EXE = r"I:\Josie-Storage\apps\aider-env\Scripts\aider.exe"
opener = build_opener(ProxyHandler({}))


def get_vram_mb() -> int:
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True
        )
        return int(res.stdout.strip().split("\n")[0])
    except Exception:
        return -1


def unload_models():
    """Unload all models from Ollama to guarantee cold VRAM baseline."""
    try:
        req = Request(f"{OLLAMA_URL}/api/ps")
        with opener.open(req, timeout=5) as res:
            data = json.loads(res.read().decode("utf-8"))
            for m in data.get("models", []):
                name = m.get("name") or m.get("model")
                if name:
                    unload_req = Request(
                        f"{OLLAMA_URL}/api/generate",
                        data=json.dumps({"model": name, "keep_alive": 0}).encode("utf-8"),
                        headers={"Content-Type": "application/json"}
                    )
                    opener.open(unload_req, timeout=5)
        time.sleep(2)
    except Exception as e:
        print(f"Warning unloading models: {e}")


def cleanup_residual_files():
    for name in [".aider.chat.history.md", ".aider.input.history"]:
        p = ROOT / name
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass


def restore_receipts():
    RECEIPTS_FILE.write_text(BASELINE_RECEIPTS_CONTENT, encoding="utf-8")


def run_aider_experiment(edit_format: str = "diff") -> dict:
    print(f"\n========================================================")
    print(f"STARTING PHASE C AIDER QUALIFICATION: edit_format={edit_format}")
    print(f"========================================================")

    restore_receipts()
    cleanup_residual_files()
    unload_models()
    baseline_vram = get_vram_mb()
    print(f"Baseline VRAM before launch: {baseline_vram} MiB")

    orders_dir = ROOT / "data" / "private" / "supervisor-work-orders"
    orders_dir.mkdir(parents=True, exist_ok=True)
    receipts_dir = ROOT / "data" / "private" / "supervisor-local-code"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    work_id = f"phase-c-aider-{edit_format}-{int(time.time())}"
    order_data = {
        "schema_version": "1",
        "job_id": work_id,
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
        "workspace": str(ROOT),
        "harness": "aider",
        "harness_executable": AIDER_EXE,
        "model": "ollama/qwen2.5-coder:14b",
        "edit_format": edit_format,
        "side_effect_capabilities": [],
        "requires_modification": True,
        "allowed_changed_paths": ["supervisor/receipts.py"],
        "read_only_paths": ["supervisor/tests/test_receipts.py"],
        "forbidden_paths": ["docs/identity", "docs/constitution", "JOSIE_CODEX_MASTER_CONTEXT.md"],
        "timeout_seconds": 360,
        "max_attempts": 2,
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
        "prompt_profile": "josie-coder-v1",
        "receipt_destination": str(receipts_dir),
        "ollama_url": "http://127.0.0.1:11434"
    }

    order_file = orders_dir / f"{work_id}.json"
    with open(order_file, "w", encoding="utf-8") as f:
        json.dump(order_data, f, indent=2)

    print(f"Work order written: {order_file}")

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from supervisor.run_job import execute

    t0 = time.perf_counter()
    receipt, receipt_path = execute(order_file)
    elapsed = time.perf_counter() - t0
    peak_vram = get_vram_mb()

    print(f"\nExecution finished in {elapsed:.2f}s | Peak VRAM: {peak_vram} MiB")
    print(f"Final Status: {receipt.get('final_status')} | Reason: {receipt.get('reason')}")
    print(f"Receipt path: {receipt_path}")

    # Read modified file and produce unified diff
    final_content = RECEIPTS_FILE.read_text(encoding="utf-8")
    diff = "".join(difflib.unified_diff(
        BASELINE_RECEIPTS_CONTENT.splitlines(keepends=True),
        final_content.splitlines(keepends=True),
        fromfile="baseline/receipts.py",
        tofile="actual/receipts.py"
    ))

    # Test execution
    test_run = subprocess.run(
        ["python", "-m", "unittest", "supervisor/tests/test_receipts.py"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    unit_test_passed = (test_run.returncode == 0)
    print(f"Unit test return code: {test_run.returncode}")
    print(f"Unit test output:\n{test_run.stderr.strip() or test_run.stdout.strip()}")

    # Check stdout/stderr log
    stdout_text = ""
    stderr_text = ""
    if receipt.get("stdout_path") and Path(receipt["stdout_path"]).exists():
        stdout_text = Path(receipt["stdout_path"]).read_text(encoding="utf-8", errors="replace")
    if receipt.get("stderr_path") and Path(receipt["stderr_path"]).exists():
        stderr_text = Path(receipt["stderr_path"]).read_text(encoding="utf-8", errors="replace")

    summary = {
        "job_id": work_id,
        "harness": "aider",
        "edit_format": edit_format,
        "model": "ollama/qwen2.5-coder:14b",
        "elapsed_sec": elapsed,
        "baseline_vram_mb": baseline_vram,
        "peak_vram_mb": peak_vram,
        "final_status": receipt.get("final_status"),
        "reason": receipt.get("reason"),
        "receipt_id": receipt.get("receipt_id"),
        "receipt_path": str(receipt_path),
        "changed_files": receipt.get("changed_files", []),
        "diff": diff,
        "unit_test_passed": unit_test_passed,
        "unit_test_output": test_run.stderr.strip() or test_run.stdout.strip(),
        "stdout_tail": stdout_text[-2000:] if stdout_text else "",
        "stderr_tail": stderr_text[-2000:] if stderr_text else "",
        "attempts": receipt.get("attempt", 1),
    }
    return summary


def main():
    report = {
        "benchmark": "Phase C - Sovereign Coder Qualification (Aider Challenger)",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runs": {}
    }

    result = run_aider_experiment(edit_format="diff")
    report["runs"]["diff"] = result

    report_path = ROOT / "reports" / "phase_c_aider_qualification.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n========================================================")
    print(f"Phase C qualification report saved: {report_path}")
    print(f"========================================================")


if __name__ == "__main__":
    main()
