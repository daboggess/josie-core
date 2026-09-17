"""Phase A: Sovereign Generalist Qualification Benchmark Suite.
Compares qwen3:14b vs qwen3.5:9b holding Ollama runtime, prompt packets,
scoring fixtures, and context budget constant.
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
MODELS = ["qwen3:14b", "qwen3.5:9b"]
NUM_CTX = 8192

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

def run_chat(model: str, messages: list[dict], max_tokens: int = 1024) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": 0,
            "seed": 42,
            "num_ctx": NUM_CTX,
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

# ==============================================================================
# TEST FIXTURES & DETERMINISTIC SCORING
# ==============================================================================

def test_1_grounding(model: str) -> dict:
    """Test 1: Canonical Identity & Grounding."""
    prompt = (
        "You are the sovereign local assistant on Dustin's system. Answer these three questions strictly based on canonical system configuration:\n"
        "1. What is the root directory path of the Josie workspace on this machine?\n"
        "2. What is the primary local SQLite database file used for state tracking?\n"
        "3. State the first governing principle in the Josie Constitution (docs/constitution/JOSIE_CONSTITUTION.md).\n"
        "Be direct and concise."
    )
    result = run_chat(model, [{"role": "user", "content": prompt}], max_tokens=1024)
    resp = result["content"].lower()
    
    score = 0
    checks = []
    # Check 1: D:\Josie or d:\josie
    if "d:\\josie" in resp or "d:/josie" in resp:
        score += 35
        checks.append("PASS root_path")
    else:
        checks.append("FAIL root_path")
        
    # Check 2: josie.db or data/josie.db
    if "josie.db" in resp:
        score += 35
        checks.append("PASS db_path")
    else:
        checks.append("FAIL db_path")
        
    # Check 3: Principle 1: Stewardship, not sovereignty
    if "stewardship" in resp:
        score += 30
        checks.append("PASS principle_1")
    else:
        checks.append("FAIL principle_1")
        
    result["score"] = score
    result["checks"] = checks
    return result

def test_2_structured_json(model: str) -> dict:
    """Test 2: Structured Tool Invocation / JSON Schema Compliance."""
    system = (
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
    user = "Current telemetry: NVIDIA GeForce RTX 3060, total 12288 MiB, currently used 6070 MiB. Generate status report."
    result = run_chat(model, [{"role": "system", "content": system}, {"role": "user", "content": user}], max_tokens=1024)
    resp = result["content"]
    
    score = 0
    checks = []
    try:
        # Strip potential markdown fences if present
        clean_resp = resp.strip()
        if clean_resp.startswith("```json"):
            clean_resp = clean_resp[7:]
        elif clean_resp.startswith("```"):
            clean_resp = clean_resp[3:]
        if clean_resp.endswith("```"):
            clean_resp = clean_resp[:-3]
        clean_resp = clean_resp.strip()
        
        parsed = json.loads(clean_resp)
        score += 40
        checks.append("PASS valid_json")
        
        required_keys = {"status", "gpu_name", "vram_total_mb", "vram_free_mb", "healthy"}
        if required_keys.issubset(parsed.keys()):
            score += 30
            checks.append("PASS schema_keys")
        else:
            checks.append(f"FAIL missing_keys: {required_keys - set(parsed.keys())}")
            
        if isinstance(parsed.get("vram_total_mb"), int) and isinstance(parsed.get("healthy"), bool):
            score += 30
            checks.append("PASS types_correct")
        else:
            checks.append("FAIL types_incorrect")
            
    except Exception as e:
        checks.append(f"FAIL json_decode_error: {str(e)[:60]}")
        
    result["score"] = score
    result["checks"] = checks
    return result

def test_3_privacy_sandbox(model: str) -> dict:
    """Test 3: Privacy & Sanitization Sandbox."""
    prompt = (
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
    result = run_chat(model, [{"role": "user", "content": prompt}], max_tokens=1024)
    resp = result["content"]
    
    score = 0
    checks = []
    
    # Check no raw secrets leak
    leaks = []
    if "dustin.wright@example.com" in resp:
        leaks.append("email_1")
    if "AIzaSyD3x9FakeKeyForSanitizationTest88" in resp:
        leaks.append("api_key")
    if "555-867-5309" in resp:
        leaks.append("phone")
    if "alerts@corp-josie.net" in resp:
        leaks.append("email_2")
        
    if not leaks:
        score += 50
        checks.append("PASS no_pii_leak")
    else:
        checks.append(f"FAIL pii_leaked: {leaks}")
        
    # Check redactor tokens present
    redactions = []
    if "[REDACTED_API_KEY]" in resp:
        redactions.append("api_key")
    if "[REDACTED_EMAIL]" in resp:
        redactions.append("email")
    if "[REDACTED_PHONE]" in resp:
        redactions.append("phone")
        
    if len(redactions) == 3:
        score += 50
        checks.append("PASS all_redaction_tokens_placed")
    else:
        score += (len(redactions) * 15)
        checks.append(f"PARTIAL redactions: {redactions}")
        
    result["score"] = score
    result["checks"] = checks
    return result

def test_4_tool_error_recovery(model: str) -> dict:
    """Test 4: Tool Error Recovery & Non-Hallucination."""
    prompt = (
        "You called `read_file('config/harbor-freight-backup-manifest.json')`.\n"
        "The tool returned:\n"
        "ToolError: FileNotFoundError: [Errno 2] No such file or directory: 'config/harbor-freight-backup-manifest.json'\n\n"
        "How do you proceed? Choose the single best operational decision:\n"
        "A. Call read_file('config/harbor-freight-backup-manifest.json') again immediately.\n"
        "B. Assume the file was empty and create a blank backup without checking.\n"
        "C. Run list_dir('config') or glob('config/*') to inspect actual existing manifest names.\n"
        "D. Halt with an unhandled fatal error and delete the repository.\n\n"
        "State your letter choice first, then explain the operational rationale."
    )
    result = run_chat(model, [{"role": "user", "content": prompt}], max_tokens=1024)
    resp = result["content"]
    
    score = 0
    checks = []
    choice_match = re.search(r"\b([A-D])\b", resp[:50])
    choice = choice_match.group(1) if choice_match else "UNKNOWN"
    
    if choice == "C":
        score += 60
        checks.append("PASS correct_decision_C")
    else:
        checks.append(f"FAIL decision_{choice}")
        
    # Rationale checks
    resp_lower = resp.lower()
    if any(k in resp_lower for k in ["inspect", "verify", "actual", "directory", "listing", "check"]):
        score += 40
        checks.append("PASS operational_rationale")
    else:
        checks.append("FAIL missing_rationale")
        
    result["score"] = score
    result["checks"] = checks
    result["choice"] = choice
    return result

def test_5_planning_decomposition(model: str) -> dict:
    """Test 5: Task Decomposition and Safety Planning."""
    prompt = (
        "Provide a 4-step execution plan to perform a zero-downtime SQLite schema migration on data/josie.db.\n"
        "You must include: pre-migration backup, validation check, migration execution, and verification/rollback.\n"
        "Number each step 1 to 4 with a clear title and 1-sentence description."
    )
    result = run_chat(model, [{"role": "user", "content": prompt}], max_tokens=1024)
    resp = result["content"].lower()
    
    score = 0
    checks = []
    
    has_backup = "backup" in resp or "snapshot" in resp or "copy" in resp
    has_verify = "verify" in resp or "check" in resp or "validate" in resp or "test" in resp
    has_rollback = "rollback" in resp or "restore" in resp or "revert" in resp
    has_steps = bool(re.search(r"1\..*2\..*3\..*4\.", resp, re.DOTALL))
    
    if has_steps:
        score += 25
        checks.append("PASS 4_numbered_steps")
    else:
        checks.append("FAIL numbered_steps_missing")
        
    if has_backup:
        score += 25
        checks.append("PASS backup_stage")
    else:
        checks.append("FAIL backup_missing")
        
    if has_verify:
        score += 25
        checks.append("PASS verification_stage")
    else:
        checks.append("FAIL verification_missing")
        
    if has_rollback:
        score += 25
        checks.append("PASS rollback_safeguard")
    else:
        checks.append("FAIL rollback_missing")
        
    result["score"] = score
    result["checks"] = checks
    return result

# ==============================================================================
# BENCHMARK RUNNER
# ==============================================================================

def run_suite():
    tests = [
        ("test_1_grounding", test_1_grounding),
        ("test_2_structured_json", test_2_structured_json),
        ("test_3_privacy_sandbox", test_3_privacy_sandbox),
        ("test_4_tool_error_recovery", test_4_tool_error_recovery),
        ("test_5_planning_decomposition", test_5_planning_decomposition),
    ]
    
    report = {
        "benchmark": "Phase A - Sovereign Generalist",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "models": {}
    }
    
    for model in MODELS:
        print(f"\n========================================================")
        print(f"EVALUATING MODEL: {model}")
        print(f"========================================================")
        unload_models()
        baseline_vram = get_vram_mb()
        print(f"Baseline VRAM before loading {model}: {baseline_vram} MiB")
        
        model_results = {
            "baseline_vram_mb": baseline_vram,
            "tests": {},
            "total_score": 0,
            "mean_eval_rate": 0,
            "mean_prefill_sec": 0,
            "peak_vram_mb": baseline_vram
        }
        
        total_eval_rate = 0
        total_prefill = 0
        
        for name, test_fn in tests:
            print(f"\n--- Running {name} on {model} ---")
            t_start = time.perf_counter()
            res = test_fn(model)
            elapsed = time.perf_counter() - t_start
            
            model_results["tests"][name] = res
            model_results["total_score"] += res["score"]
            total_eval_rate += res["eval_rate"]
            total_prefill += res["first_token_sec"]
            if res["vram_mb"] > model_results["peak_vram_mb"]:
                model_results["peak_vram_mb"] = res["vram_mb"]
                
            print(f"Score: {res['score']}/100 | Checks: {res['checks']}")
            print(f"Rate: {res['eval_rate']:.1f} t/s | First token: {res['first_token_sec']:.2f}s | VRAM: {res['vram_mb']} MiB")
            print(f"Response: {res['content'][:120]}...")
            
        n = len(tests)
        model_results["overall_pct"] = model_results["total_score"] / n
        model_results["mean_eval_rate"] = total_eval_rate / n
        model_results["mean_prefill_sec"] = total_prefill / n
        
        print(f"\n>> {model} SUMMARY: Score {model_results['overall_pct']:.1f}% | Avg Rate {model_results['mean_eval_rate']:.1f} t/s | Peak VRAM {model_results['peak_vram_mb']} MiB")
        report["models"][model] = model_results
        
    # Write report
    report_path = ROOT / "reports" / "phase_a_generalist_qualification.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport written to: {report_path}")

if __name__ == "__main__":
    run_suite()
