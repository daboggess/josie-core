"""One opt-in, bounded Ollama benchmark; no history/config writes or cloud calls."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
MODEL = "josie-local:1.0"
PROMPT = (
    "Explain why keeping backups and checking evidence are useful when maintaining "
    "a computer. Use exactly three short bullet points, no introduction, and no "
    "more than 90 words. Do not claim to have inspected this computer."
)
OPTIONS = {"temperature": 0, "seed": 42, "num_ctx": 4096, "num_thread": 3, "num_predict": 128}
URL = "http://127.0.0.1:11434"


class MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.DWORD), ("load", wintypes.DWORD),
        ("total_physical", ctypes.c_ulonglong), ("available_physical", ctypes.c_ulonglong),
        ("total_pagefile", ctypes.c_ulonglong), ("available_pagefile", ctypes.c_ulonglong),
        ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
        ("extended_virtual", ctypes.c_ulonglong),
    ]


def sample():
    memory = MemoryStatus()
    memory.length = ctypes.sizeof(memory)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        raise OSError("Windows memory metrics unavailable")
    idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        raise OSError("Windows CPU metrics unavailable")
    tick = lambda x: (x.dwHighDateTime << 32) | x.dwLowDateTime
    return {
        "used_ram_bytes": memory.total_physical - memory.available_physical,
        "available_ram_bytes": memory.available_physical,
        "total_ram_bytes": memory.total_physical,
        "idle": tick(idle), "total_cpu_ticks": tick(kernel) + tick(user),
    }


def paging():
    result = subprocess.run(
        [os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                      r"System32\WindowsPowerShell\v1.0\powershell.exe"),
         "-NoProfile", "-NonInteractive", "-Command",
         "Get-CimInstance Win32_PageFileUsage | Select-Object Name,AllocatedBaseSize,CurrentUsage,PeakUsage | ConvertTo-Json -Compress"],
        capture_output=True, text=True, timeout=12,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        return json.loads(result.stdout)
    except ValueError:
        return {"status": "unavailable"}


def measure():
    if os.name != "nt":
        raise RuntimeError("Run on the Windows host with Josie's existing Python")
    if (ROOT / ".git/josie-delegate.lock").exists():
        raise RuntimeError("Delegation lock present; no inference started")
    opener = build_opener(ProxyHandler({}))
    def get(path):
        with opener.open(URL + path, timeout=5) as response:
            return json.load(response)
    tags = get("/api/tags")
    definition = next((x for x in tags["models"] if x["name"] == MODEL), None)
    if definition is None:
        raise RuntimeError("Expected installed model is absent; no download attempted")
    before_models = get("/api/ps")["models"]
    if before_models:
        raise RuntimeError("A model is already resident; wait for normal expiry, do not evict it")
    page_before = paging()
    before = sample()
    samples = [before]
    stop = threading.Event()
    def monitor():
        while not stop.wait(0.25):
            samples.append(sample())
    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    first_token = None
    final = None
    text = []
    payload = {"model": MODEL, "messages": [{"role": "user", "content": PROMPT}],
               "stream": True, "options": OPTIONS}
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    start = time.perf_counter()
    # Socket timeout plus a wall-clock watchdog; closes only this request.
    response = None
    watchdog = None
    try:
        request = Request(URL + "/api/chat", data=json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
        response = opener.open(request, timeout=120)
        watchdog = threading.Timer(max(0.01, 120 - (time.perf_counter() - start)), response.close)
        watchdog.daemon = True
        watchdog.start()
        for line in response:
            if time.perf_counter() - start > 120:
                raise TimeoutError("Benchmark exceeded 120 seconds")
            event = json.loads(line)
            if event.get("error"):
                raise RuntimeError("Ollama returned an inference error")
            content = event.get("message", {}).get("content", "")
            if content and first_token is None:
                first_token = time.perf_counter() - start
            text.append(content)
            if event.get("done"):
                final = event
                break
    finally:
        if watchdog:
            watchdog.cancel()
        if response:
            response.close()
        stop.set()
        monitor_thread.join(timeout=2)
    elapsed = time.perf_counter() - start
    after = sample()
    samples.append(after)
    if final is None or first_token is None:
        raise RuntimeError("No completed response; do not treat partial output as a baseline")
    duration = final.get("eval_duration", 0) / 1e9
    cpu_delta = after["total_cpu_ticks"] - before["total_cpu_ticks"]
    return {
        "started_at": started_at, "model": MODEL, "model_digest": definition["digest"],
        "model_bytes": definition["size"], "prompt": PROMPT, "options": OPTIONS,
        "sampling_interval_seconds": 0.25, "sample_count": len(samples),
        "model_resident_before": before_models, "model_resident_after": get("/api/ps")["models"],
        "ram_before_bytes": before["used_ram_bytes"],
        "ram_peak_observed_bytes": max(x["used_ram_bytes"] for x in samples),
        "ram_after_bytes": after["used_ram_bytes"], "total_ram_bytes": before["total_ram_bytes"],
        "system_cpu_average_percent": round(100 * (1 - (after["idle"] - before["idle"]) / cpu_delta), 2),
        "pagefile_before": page_before, "pagefile_after": paging(),
        "time_to_first_content_seconds": round(first_token, 4),
        "wall_response_seconds": round(elapsed, 4),
        "output_tokens": final.get("eval_count"),
        "output_tokens_per_second": round(final.get("eval_count", 0) / duration, 3) if duration else None,
        "load_seconds": final.get("load_duration", 0) / 1e9,
        "prompt_eval_seconds": final.get("prompt_eval_duration", 0) / 1e9,
        "generation_seconds": duration, "done_reason": final.get("done_reason"),
        "response_sha256": hashlib.sha256("".join(text).encode()).hexdigest(),
        "response": "".join(text), "history_writes": 0, "cloud_calls": 0,
        "notes": "Cold Ollama residency, not a cold filesystem cache. CPU/RAM are host-wide, not process-isolated. Normal service logs and temporary model residency may change.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Explicitly permit one local inference request")
    args = parser.parse_args(argv)
    if not args.run:
        print("WARN: No inference performed. Pass --run only when no chat/job is active.")
        return 0
    try:
        print(json.dumps(measure(), indent=2))
        return 0
    except Exception as exc:
        print("FAIL: Benchmark incomplete (" + type(exc).__name__ + "); no service/config changes attempted.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
