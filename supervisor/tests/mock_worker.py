from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


command = sys.argv[1]
if command == "allowed":
    Path("allowed.txt").write_text("OK", encoding="utf-8")
elif command == "unauthorized":
    Path("allowed.txt").write_text("OK", encoding="utf-8")
    Path("intruder.txt").write_text("NO", encoding="utf-8")
elif command == "nonzero":
    raise SystemExit(7)
elif command == "allowed_and_db":
    Path("allowed.txt").write_text("OK", encoding="utf-8")
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    (data_dir / "josie.db").write_text("concurrent db update", encoding="utf-8")
elif command == "allowed_and_wal_shm":
    Path("allowed.txt").write_text("OK", encoding="utf-8")
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    (data_dir / "josie.db-wal").write_text("wal data", encoding="utf-8")
    (data_dir / "josie.db-shm").write_text("shm data", encoding="utf-8")
elif command == "allowed_and_unrelated_db":
    Path("allowed.txt").write_text("OK", encoding="utf-8")
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    (data_dir / "unrelated.db").write_text("unrelated db data", encoding="utf-8")
elif command == "worker_targeted_db":
    import json
    print(json.dumps({"type": "tool_use", "part": {"tool": "write", "state": {"status": "completed", "input": {"filePath": "data/josie.db"}}}}))
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    (data_dir / "josie.db").write_text("worker touched db", encoding="utf-8")
elif command == "blocked_prose_after_pass":
    Path("allowed.txt").write_text("OK", encoding="utf-8")
    print("### Blocked\nThe maximum number of steps allowed for this task has been reached.")
elif command == "genuine_blocker_fail":
    print("### Blocked\n- missing required PostgreSQL dependency in host environment")
elif command == "step_limit_fail":
    print("### Blocked\n- The maximum number of steps allowed for this task has been reached.")
elif command.startswith("timeout:"):
    pid_file = Path(command.split(":", 1)[1])
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    pid_file.write_text(str(child.pid), encoding="ascii")
    time.sleep(120)
