import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"D:\Josie")
TEST_DIR = ROOT / "tmp" / "aider_smoke_test"
TEST_DIR.mkdir(parents=True, exist_ok=True)

test_file = TEST_DIR / "test_math.py"
test_file.write_text("def add(a, b):\n    pass\n", encoding="utf-8")

aider_exe = r"I:\Josie-Storage\apps\aider-env\Scripts\aider.exe"
env = dict(os.environ)
env["OLLAMA_API_BASE"] = "http://127.0.0.1:11434"

cmd = [
    aider_exe,
    "--model", "ollama/qwen2.5-coder:14b",
    "--edit-format", "whole",
    "--yes-always",
    "--no-git",
    "--no-auto-commits",
    "--no-analytics",
    "--no-check-update",
    "--message", "Implement add(a, b) to return a + b.",
    str(test_file)
]

print("Running Aider smoke test...")
proc = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(TEST_DIR), timeout=120)
print("Return code:", proc.returncode)
print("STDOUT:\n", proc.stdout[:500])
print("STDERR:\n", proc.stderr[:500])
print("\nFinal content of test_math.py:\n", test_file.read_text(encoding="utf-8"))
