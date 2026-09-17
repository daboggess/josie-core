"""Corrective evaluation of qwen3.5:9b under two operating modes:
Mode 1: Operational / Direct (think: false)
Mode 2: Deep Reasoning (think: true, budget: 2048)
Compared against resident qwen3:14b.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from urllib.request import build_opener, ProxyHandler, Request

ROOT = Path(r"D:\Josie")
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

def run_chat(model: str, messages: list[dict], think: bool = False, max_tokens: int = 1024) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "think": think,
        "stream": True,
        "options": {
            "temperature": 0,
            "seed": 42,
            "num_ctx": 8192,
            "num_predict": max_tokens
        }
    }
    req = Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    t0 = time.perf_counter()
    res = opener.open(req, timeout=120)
    first_token_time = None
    content_chunks = []
    thinking_chunks = []
    final_data = {}
    
    for line in res:
        if not line:
            continue
        chunk = json.loads(line.decode("utf-8"))
        msg = chunk.get("message", {})
        if "thinking" in msg and msg["thinking"]:
            if first_token_time is None:
                first_token_time = time.perf_counter() - t0
            thinking_chunks.append(msg["thinking"])
        if "content" in msg and msg["content"]:
            if first_token_time is None:
                first_token_time = time.perf_counter() - t0
            content_chunks.append(msg["content"])
        if chunk.get("done"):
            final_data = chunk
            break
            
    total_elapsed = time.perf_counter() - t0
    eval_count = final_data.get("eval_count", 0)
    eval_dur = final_data.get("eval_duration", 1) / 1e9
    pe_count = final_data.get("prompt_eval_count", 0)
    pe_dur = final_data.get("prompt_eval_duration", 1) / 1e9
    
    return {
        "first_token_sec": first_token_time or total_elapsed,
        "total_time_sec": total_elapsed,
        "content": "".join(content_chunks).strip(),
        "thinking": "".join(thinking_chunks).strip(),
        "eval_count": eval_count,
        "eval_rate": eval_count / max(0.001, eval_dur),
        "prompt_eval_count": pe_count,
        "prompt_eval_rate": pe_count / max(0.001, pe_dur),
        "vram_mb": get_vram_mb()
    }

def test_operational_mode():
    print("\n========================================================")
    print("MODE 1: OPERATIONAL / DIRECT (qwen3.5:9b, think: False)")
    print("========================================================")
    
    # 1. Structured JSON
    sys_prompt = (
        "You are a local hardware telemetry agent. Respond ONLY with a valid JSON object conforming to this schema:\n"
        "{\n"
        '  "status": "OK" | "WARNING" | "CRITICAL",\n'
        '  "gpu_name": string,\n'
        '  "vram_total_mb": integer,\n'
        '  "vram_free_mb": integer,\n'
        '  "healthy": boolean\n'
        "}\n"
        "Do not include markdown code blocks, conversational greetings, or explanations outside the JSON."
    )
    user_prompt = "Current telemetry: NVIDIA GeForce RTX 3060, total 12288 MiB, currently used 6070 MiB. Generate status report."
    res_json = run_chat("qwen3.5:9b", [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}], think=False, max_tokens=256)
    print(f"\n1. Structured JSON (think: False):")
    print(f"   Time: {res_json['total_time_sec']:.2f}s | Rate: {res_json['eval_rate']:.1f} t/s | Tokens: {res_json['eval_count']}")
    print(f"   Output: {res_json['content']}")
    
    # 2. Privacy Sandbox
    privacy_prompt = (
        "You are a local sovereign security filter. Sanitize the following log excerpt before it leaves the machine.\n"
        "Replace all Google API keys with `[REDACTED_API_KEY]`.\n"
        "Replace all email addresses with `[REDACTED_EMAIL]`.\n"
        "Replace all phone numbers with `[REDACTED_PHONE]`.\n"
        "Preserve timestamps, formatting, and all other text verbatim.\n\n"
        "Log excerpt:\n"
        "2026-09-11 14:01:10 INFO User login dustin.wright@example.com from 192.168.1.50\n"
        "2026-09-11 14:01:12 ERROR Cloud proxy rejected key AIzaSyD3x9FakeKeyForSanitizationTest88 with 403\n"
        "2026-09-11 14:01:15 WARN On-call Dustin reached at 555-867-5309 or alerts@corp-josie.net"
    )
    res_priv = run_chat("qwen3.5:9b", [{"role": "user", "content": privacy_prompt}], think=False, max_tokens=512)
    print(f"\n2. Privacy Sandbox (think: False):")
    print(f"   Time: {res_priv['total_time_sec']:.2f}s | Rate: {res_priv['eval_rate']:.1f} t/s | Tokens: {res_priv['eval_count']}")
    print(f"   Output:\n{res_priv['content']}")
    
    # 3. Tool Error Recovery
    tool_prompt = (
        "You called `read_file('config/harbor-freight-backup-manifest.json')`.\n"
        "The tool returned:\n"
        "ToolError: FileNotFoundError: [Errno 2] No such file or directory: 'config/harbor-freight-backup-manifest.json'\n\n"
        "How do you proceed? Choose the single best operational decision:\n"
        "A. Call read_file('config/harbor-freight-backup-manifest.json') again immediately.\n"
        "B. Assume the file was empty and create a blank backup without checking.\n"
        "C. Run list_dir('config') or glob('config/*') to inspect actual existing manifest names.\n"
        "D. Halt with an unhandled fatal error and delete the repository.\n\n"
        "State your letter choice first, then explain the operational rationale concisely."
    )
    res_tool = run_chat("qwen3.5:9b", [{"role": "user", "content": tool_prompt}], think=False, max_tokens=256)
    print(f"\n3. Tool Error Recovery (think: False):")
    print(f"   Time: {res_tool['total_time_sec']:.2f}s | Rate: {res_tool['eval_rate']:.1f} t/s | Tokens: {res_tool['eval_count']}")
    print(f"   Output:\n{res_tool['content']}")
    
    # 4. Routine Planning
    plan_prompt = (
        "Provide a 4-step execution plan to perform a zero-downtime SQLite schema migration on data/josie.db.\n"
        "You must include: pre-migration backup, validation check, migration execution, and verification/rollback.\n"
        "Number each step 1 to 4 with a clear title and 1-sentence description."
    )
    res_plan = run_chat("qwen3.5:9b", [{"role": "user", "content": plan_prompt}], think=False, max_tokens=512)
    print(f"\n4. Routine Planning (think: False):")
    print(f"   Time: {res_plan['total_time_sec']:.2f}s | Rate: {res_plan['eval_rate']:.1f} t/s | Tokens: {res_plan['eval_count']}")
    print(f"   Output:\n{res_plan['content']}")
    
    print("\n========================================================")
    print("MODE 2: DEEP REASONING (qwen3.5:9b, think: True, budget: 2048)")
    print("========================================================")
    reasoning_prompt = (
        "Analyze this system conflict: We have an offline SQLite database with WAL mode enabled. A background backup service copies josie.db while active transactions are in flight. Occasionally, the copied file fails integrity check on another host. Why does this happen, and what is the exact atomic backup sequence required to prevent corruption without taking the database offline?"
    )
    res_reason = run_chat("qwen3.5:9b", [{"role": "user", "content": reasoning_prompt}], think=True, max_tokens=2048)
    print(f"\nDeep Reasoning Task:")
    print(f"   Time: {res_reason['total_time_sec']:.2f}s | Rate: {res_reason['eval_rate']:.1f} t/s | Total Tokens: {res_reason['eval_count']}")
    print(f"   Thinking Tokens: {len(res_reason['thinking'].split())} words")
    print(f"   Content Length: {len(res_reason['content'])} chars")
    print(f"   Content Preview:\n{res_reason['content'][:300]}...\n")
    
    results = {
        "mode1_json": res_json,
        "mode1_privacy": res_priv,
        "mode1_tool": res_tool,
        "mode1_plan": res_plan,
        "mode2_deep_reasoning": res_reason
    }
    with open(ROOT / "reports" / "qwen35_thinking_correction.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("Report saved to reports/qwen35_thinking_correction.json")

if __name__ == "__main__":
    test_operational_mode()
