# Pre-GPU baseline — 2026-08-28

## Scope and identity

One short, bounded local test, not a performance campaign. No NVIDIA GPU was detected. Ollama's post-request residency reported **0 GPU bytes**, so this run establishes CPU-only inference for the actual current chat model.

- Starting Git branch: local-agent-runtime.
- Starting HEAD: da6eccfb459e4f74f16301663cefa2acab8a8f8c.
- Pre-existing dirty Compose setting and phone proof are recorded in [CURRENT_STATE.md](CURRENT_STATE.md).
- Windows 11 Pro 10.0.26200; Intel i7-7700, 4 cores/8 threads.
- RAM: 34,274,889,728 bytes (31.92 GiB); Intel HD Graphics 630.
- Native Ollama 0.32.5; models/executable on external D:; WebUI v0.11.1.
- Model **josie-local:1.0**, 1.5B, Q4_K_M, logical size **986,063,150 bytes** (about 0.918 GiB).
- Model digest: `4bb061b78eb1775269156342b614d1170e04694eab0a499613926ddcc7ffc47c`.
- No resident Ollama model before the request. This is cold **Ollama residency**, not a flushed filesystem cache.
- No cloud calls, tools or history writes. Normal server logs/model residency may change.

This is **not** an 8B local-agent benchmark. Existing local delegation uses another model/context and has much longer CPU latency.

## Repeatable request

Started **2026-08-28T10:54:49-0400**.

Exact prompt:

> Explain why keeping backups and checking evidence are useful when maintaining a computer. Use exactly three short bullet points, no introduction, and no more than 90 words. Do not claim to have inspected this computer.

Options:

```json
{"temperature": 0, "seed": 42, "num_ctx": 4096, "num_thread": 3, "num_predict": 128}
```

The fixed request uses streamed Ollama /api/chat with one user message. The model's existing system prompt remains part of the model. No new prompt/configuration is installed.

Run from a normal Windows PowerShell terminal only when no chat/job is active:

```powershell
Set-Location C:/Josie
.venv/Scripts/python.exe -B scripts/measure_pre_gpu.py --run
```

The script defaults to **no inference** without --run. It refuses a present delegation lock, missing model or any resident model; it does not evict, pull or install. Wait for normal keep-alive expiry. It limits output to 128 tokens and bounds the request to approximately 120 seconds with a socket timeout and response-close watchdog. Results go to stdout, not SQLite or source files.

## Measured result

| Metric | CPU-only result |
| --- | ---: |
| Time to first nonempty streamed content | **4.9458 s** |
| Total wall response time | **6.7645 s** |
| Ollama model load | 1.8047396 s |
| Prompt evaluation | 3.122425 s |
| Generation | 1.818388 s |
| Generated tokens reported by Ollama | 41 |
| Generation speed (41 / eval duration) | **22.547 tokens/s** |
| Completion | stop, complete response |
| Host RAM before | 12,233,326,592 bytes, approximately 11.39 GiB |
| Peak sampled host RAM | 13,472,980,992 bytes, approximately 12.55 GiB |
| Host RAM after | 13,433,917,440 bytes |
| Host-wide average CPU utilization | **37.27%** across all logical processors |
| Sampling | 250 ms, 28 samples |
| Resident model after | 1,169,980,128 bytes; context 4096 |
| GPU allocation after | **0 bytes** |
| Pagefile allocation | 2,048 MiB |
| Pagefile usage before / after | **52 / 52 MiB** |
| Pagefile peak since boot | 880 MiB, not peak attributable to this request |
| CPU temperature | Unavailable from existing ACPI query |
| GPU temperature / VRAM | No NVIDIA device yet |
| Inference errors | None reported |

Response SHA-256: `0dd4a925f96b867f32875e88a00ce2c7f2d4b6ad4daeedbb40f345b78733ca2d`. Generated advice is not machine-state evidence; the response hash is a comparison aid, not an expected assertion about the computer.

## Interpretation and limits

- CPU and RAM are host-wide, including Docker, this app and other background work; not isolated Ollama process accounting.
- First streamed content approximates first-token latency; streaming chunk boundaries are not token boundaries.
- Generation tokens/s excludes loading/prompt evaluation. End-to-end speed must use total wall time separately.
- The 250 ms samples may miss a brief memory peak. Only one run was made, so this is a reference point, not a statistically stable ranking.
- The USB model store, CPU-only inference and startup/prompt evaluation can affect latency. This run does not isolate a single bottleneck.
- No new sensor tools were installed; absence of temperature data is explicitly unknown.
- C: free space was about 18.42 GiB at inventory and 18.60 GiB at the later doctor check. Background activity explains changing live readings; these are not fixed properties.

## Verification of this documentation checkpoint

- Before changes: **157/157 tests passed**, 38.705 seconds.
- New focused diagnostics: **10/10 passed**.
- After diagnostics added: **167/167 tests passed**, 37.787 seconds.
- Git Bash syntax check passed.
- Live doctor: **71 PASS / 10 WARN / 0 FAIL**, exit 0.
- All six local health endpoints responded; four existing Docker containers healthy.
- Main SQLite and WebUI SQLite read-only quick_check passed.
- Both 2026-08-28 daily SQLite backups restored into isolated in-memory databases and passed full integrity_check (39 tables each); production untouched.
- Warnings: Unix load metric not applicable, low C: headroom, broad Ollama firewall rules, Docker auto-start disabled, idle GPU usage inconclusive, stale full-service backup, no NVIDIA/tooling/VRAM yet, and one old GPU-related log match.
- No service restarts, new cloud calls, history imports, model changes or NVIDIA/CUDA installation.

A checkpoint commit covers these docs/diagnostics only. Existing Compose/phone-proof changes remain outside it. See [BACKUP_CHECKLIST.md](BACKUP_CHECKLIST.md) for what Git does not recover.

## After GPU installation

Keep this file immutable as the comparison record. Run the same script with the same model digest, options, idle conditions and Ollama version first. Capture new output in a **separate post-GPU report** and record driver, GPU/VRAM allocation and any version changes. Compare first content, total time, tokens/s, CPU/RAM, paging, errors and available temperatures. Only then consider separate model/context optimization.
