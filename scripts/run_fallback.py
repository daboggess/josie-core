from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Josie")
sys.path.insert(0, str(ROOT))

from mission_manager.ingress import continue_mission

def main():
    print("=== Step 3: Executing Fallback Worker (gemma4:12b) ===")
    start_time = time.time()
    outcome = continue_mission("qual-coder-v1-1-final", project_root=ROOT, fallback_worker="gemma4:12b")
    elapsed = time.time() - start_time

    print(f"\nFallback execution finished in {elapsed:.2f}s")
    print(f"Outcome status: {outcome.get('mission_status')}")
    print(f"Stop reason: {outcome.get('stop_reason')}")
    print(f"Latest receipt: {outcome.get('latest_authoritative_receipt')}")
    print(f"Message:\n{outcome.get('assistant_message')}")

if __name__ == "__main__":
    main()
