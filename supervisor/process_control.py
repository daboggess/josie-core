from __future__ import annotations

import ctypes
import datetime as dt
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


CREATE_NEW_PROCESS_GROUP = 0x00000200
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong),
        ("th32ProcessID", ctypes.c_ulong), ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", ctypes.c_ulong), ("cntThreads", ctypes.c_ulong),
        ("th32ParentProcessID", ctypes.c_ulong), ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", ctypes.c_ulong), ("szExeFile", ctypes.c_wchar * 260),
    ]


def timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def descendant_pids(pid: int) -> list[int]:
    if os.name != "nt":
        return []
    kernel = ctypes.windll.kernel32
    snapshot = kernel.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return []
    pairs: list[tuple[int, int]] = []
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    try:
        ok = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            pairs.append((int(entry.th32ProcessID), int(entry.th32ParentProcessID)))
            ok = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    found: set[int] = set()
    frontier = {pid}
    while frontier:
        children = {child for child, parent in pairs if parent in frontier and child not in found}
        found.update(children)
        frontier = children
    return sorted(found)


def pid_exists(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        code = ctypes.c_ulong()
        active = bool(ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == STILL_ACTIVE
        ctypes.windll.kernel32.CloseHandle(handle)
        return active
    return False


def terminate_tree(pid: int) -> dict:
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True,
            creationflags=0x08000000,
        )
        for _ in range(30):
            if not pid_exists(pid):
                break
            time.sleep(0.1)
        return {"method": "taskkill_tree", "exit_code": result.returncode, "gone": not pid_exists(pid), "stdout": result.stdout, "stderr": result.stderr}
    os.killpg(pid, 9)
    return {"method": "killpg", "exit_code": 0, "gone": not pid_exists(pid)}


@dataclass
class ProcessResult:
    pid: int
    exit_code: int | None
    timed_out: bool
    elapsed_seconds: float
    cleanup: dict | None
    liveness: dict
    stalled: bool = False


def run_contained(argv: list[str], cwd: str, timeout: float, stdout_path: str, stderr_path: str,
                  env: dict[str, str] | None = None,
                  activity_probe: Callable[[], dict] | None = None,
                  meaningful_activity_probe: Callable[[], bool] | None = None,
                  stall_timeout: float | None = None) -> ProcessResult:
    flags = CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    start = time.monotonic()
    created_at = timestamp()
    first_stdout_at = None
    first_stderr_at = None
    observed_children: set[int] = set()
    runtime_observations: list[dict] = []
    meaningful_activity_at = None
    next_probe = start
    with open(stdout_path, "w", encoding="utf-8") as stdout, open(stderr_path, "w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, text=True,
            creationflags=flags, start_new_session=(os.name != "nt"), env=env,
        )
        cleanup = None
        timed_out = False
        stalled = False
        while True:
            current = time.monotonic()
            observed_children.update(descendant_pids(process.pid))
            if first_stdout_at is None and Path(stdout_path).stat().st_size:
                first_stdout_at = timestamp()
            if first_stderr_at is None and Path(stderr_path).stat().st_size:
                first_stderr_at = timestamp()
            if activity_probe is not None and current >= next_probe:
                try:
                    observation = activity_probe()
                except Exception as exc:
                    observation = {"probe_error": type(exc).__name__}
                if not runtime_observations or observation != runtime_observations[-1].get("value"):
                    runtime_observations.append({"at": timestamp(), "value": observation})
                next_probe = current + 1.0
            if meaningful_activity_at is None and meaningful_activity_probe is not None:
                try:
                    if meaningful_activity_probe():
                        meaningful_activity_at = timestamp()
                except (OSError, UnicodeError):
                    pass
            exit_code = process.poll()
            if exit_code is not None:
                break
            if (stall_timeout is not None and meaningful_activity_at is None
                    and current - start >= stall_timeout):
                stalled = True
                cleanup = terminate_tree(process.pid)
                try:
                    exit_code = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    exit_code = None
                cleanup["gone"] = not pid_exists(process.pid)
                break
            if current - start >= timeout:
                timed_out = True
                cleanup = terminate_tree(process.pid)
                try:
                    exit_code = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    exit_code = None
                cleanup["gone"] = not pid_exists(process.pid)
                break
            time.sleep(min(0.25, max(0.01, timeout - (current - start))))
    ended_at = timestamp()
    liveness = {
        "process_created": True, "process_created_at": created_at,
        "process_ended_at": ended_at, "stdin_mode": "devnull",
        "observed_child_pids": sorted(observed_children),
        "first_stdout_at": first_stdout_at, "first_stderr_at": first_stderr_at,
        "meaningful_worker_activity_observed": bool(first_stdout_at or first_stderr_at),
        "meaningful_tool_activity_observed": meaningful_activity_at is not None,
        "meaningful_tool_activity_at": meaningful_activity_at,
        "runtime_observations": runtime_observations,
    }
    return ProcessResult(process.pid, exit_code, timed_out, time.monotonic() - start,
                         cleanup, liveness, stalled)
