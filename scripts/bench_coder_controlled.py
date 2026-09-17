"""Phase B: Sovereign Coder Qualification Benchmark (Controlled Experiment).
Compares:
  Candidate A: qwen3:14b + OpenCode 1.18.23 + Supervisor
  Candidate B: qwen2.5-coder:14b + OpenCode 1.18.23 + Supervisor
Holding harness, prompt, acceptance tests, and workspace strictly constant.
"""
from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.request import build_opener, ProxyHandler, Request

ROOT = Path(r"D:\Josie")
RECEIPTS_FILE = ROOT / "supervisor" / "receipts.py"
BASELINE_RECEIPTS_CONTENT = RECEIPTS_FILE.read_text(encoding="utf-8")

OLLAMA_URL = "http://127.0.0.1:11434"
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
    """Unload all models from Ollama to guarantee cold VRAM isolation."""
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

def restore_receipts():
    RECEIPTS_FILE.write_text(BASELINE_RECEIPTS_CONTENT, encoding="utf-8")

def run_candidate(model_id: str, candidate_name: str) -> dict:
    print(f"\n========================================================")
    print(f"STARTING PHASE B QUALIFICATION: {candidate_name} ({model_id})")
    print(f"========================================================")
    
    restore_receipts()
    unload_models()
    baseline_vram = get_vram_mb()
    print(f"Baseline VRAM before launch: {baseline_vram} MiB")
    
    # Construct Work Order
    orders_dir = ROOT / "data" / "private" / "supervisor-work-orders"
    orders_dir.mkdir(parents=True, exist_ok=True)
    receipts_dir = ROOT / "data" / "private" / "supervisor-local-code"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    
    work_id = f"phase-b-{candidate_name}-{int(time.time())}"
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
        "harness": "opencode",
        "harness_executable": r"I:\Josie-Storage\apps\OpenCode\1.18.23\opencode.exe",
        "harness_config": str(ROOT / "config" / "opencode-local.json"),
        "agent": "josie-coder",
        "agent_profile": str(ROOT / ".opencode" / "agents" / "josie-coder.md"),
        "model": model_id,
        "side_effect_capabilities": [],
        "requires_modification": True,
        "allowed_changed_paths": ["supervisor/receipts.py"],
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
    
    # Import and execute via Supervisor
    import sys
    sys.path.insert(0, str(ROOT))
    from supervisor.run_job import execute
    
    t0 = time.perf_counter()
    receipt, receipt_path = execute(order_file)
    elapsed = time.perf_counter() - t0
    peak_vram = get_vram_mb()
    
    print(f"\nExecution finished in {elapsed:.2f}s | Peak VRAM: {peak_vram} MiB")
    print(f"Final Status: {receipt.get('final_status')} | Reason: {receipt.get('reason')}")
    print(f"Receipt path: {receipt_path}")
    
    # Inspect final file state and diff
    final_content = RECEIPTS_FILE.read_text(encoding="utf-8")
    diff = "".join(difflib.unified_diff(
        BASELINE_RECEIPTS_CONTENT.splitlines(keepends=True),
        final_content.splitlines(keepends=True),
        fromfile="baseline/receipts.py",
        tofile="actual/receipts.py"
    ))
    
    # Run acceptance unit tests directly to capture test output
    test_run = subprocess.run(
        ["python", "-m", "unittest", "supervisor/tests/test_receipts.py"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    unit_test_passed = (test_run.returncode == 0)
    print(f"Unit test return code: {test_run.returncode}")
    print(f"Unit test output:\n{test_run.stderr.strip() or test_run.stdout.strip()}")
    
    # Failure categorization
    reason = receipt.get("reason", "UNKNOWN")
    final_status = receipt.get("final_status", "UNKNOWN")
    failure_category = "NONE" if final_status == "PASS" else "UNCLASSIFIED"
    
    tool_activity = receipt.get("tool_activity", [])
    if final_status != "PASS":
        # Check syntax validity of receipts.py
        try:
            compile(final_content, "receipts.py", "exec")
            syntax_ok = True
        except SyntaxError as syn:
            syntax_ok = False
            syntax_err = str(syn)
            
        if not syntax_ok:
            failure_category = "HARNESS_EDIT_SYNTAX_CORRUPTION"
        elif "read" in tool_activity and "edit" not in tool_activity and "write" not in tool_activity:
            failure_category = "TOOL_READ_LOOP_NO_EDIT"
        elif not unit_test_passed:
            failure_category = "MODEL_LOGIC_ERROR_TEST_FAILED"
            
    summary = {
        "candidate": candidate_name,
        "model_id": model_id,
        "elapsed_sec": elapsed,
        "baseline_vram_mb": baseline_vram,
        "peak_vram_mb": peak_vram,
        "final_status": final_status,
        "reason": reason,
        "receipt_id": receipt.get("receipt_id"),
        "receipt_path": str(receipt_path),
        "tool_activity": tool_activity,
        "diff": diff,
        "unit_test_passed": unit_test_passed,
        "unit_test_output": test_run.stderr.strip() or test_run.stdout.strip(),
        "failure_category": failure_category
    }
    return summary

def run_phase_b():
    report = {
        "benchmark": "Phase B - Sovereign Coder (Harness Held Constant)",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "candidates": {}
    }
    
    candidates = [
        ("ollama/qwen3:14b", "qwen3-14b"),
        ("ollama/qwen2.5-coder:14b", "qwen25-coder-14b")
    ]
    
    for model_id, name in candidates:
        summary = run_candidate(model_id, name)
        report["candidates"][name] = summary
        
    # Write report
    report_path = ROOT / "reports" / "phase_b_coder_qualification.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n========================================================")
    print(f"Phase B report saved: {report_path}")
    print(f"========================================================")

if __name__ == "__main__":
    run_phase_b()
