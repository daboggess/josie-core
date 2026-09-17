# Qwen3 8B pre-GPU baseline — 2026-08-28

Separate from the unchanged `PRE_GPU_BASELINE.md` 1.5B benchmark. One bounded
direct Ollama request; no OpenCode job, cloud calls, tools, history writes or
model/service configuration changes. This measures the engineering model's
inference cost, **not** full engineering-agent latency or task success.

## Identity and repeatable request

- Host: Windows 11 Pro 10.0.26200; i7-7700, 4 cores/8 threads; 31.92 GiB RAM.
- HEAD: `49709472a5740149ebbd63c20cfe35477e5bc8c6`, `local-agent-runtime`.
- Ollama: 0.32.5, native Windows, `http://127.0.0.1:11434`.
- Exact model: `josie-qual-qwen3:8b-32k`, Qwen3 8.2B, Q4_K_M.
- Digest: `b3e2287c81ab3732bf229ac1df0e7b7d1824129fec4bc7e30b9ce361fee2d2e9`.
- Logical model size: 5,225,388,180 bytes; model store on external D:.
- Started: `2026-08-28T12:13:42-0400`.
- No resident model or delegation lock before request. Cold Ollama residency,
  not a flushed filesystem cache. No model eviction was performed.

Exact prompt:

> Review this Python function: def add(a, b): return a + b. State what add(2, 3) returns and give one deterministic assert statement that tests it. Be concise. Do not use tools or claim to inspect files.

Request: streamed `/api/chat`, one user message, options:

```json
{"temperature": 0, "seed": 42, "num_ctx": 32768, "num_predict": 256}
```

The context matches the installed alias; temperature matches the existing
engineering agent. Seed and token cap bound this benchmark only. No thread
override, thinking override, system-message replacement or persistent tuning.
Existing model stop/sampling parameters remain inherited. Reasoning stays enabled.

Repeat **unchanged**, after normal model expiry and with no chat/job active:

```powershell
Set-Location C:/Josie
.venv/Scripts/python.exe -B scripts/measure_qwen3_pre_gpu.py --run
```

Without `--run`, no inference occurs. The script reuses existing Windows metric
helpers, refuses active delegation/resident models, does not pull models, and
prints results to stdout. It uses a 600-second socket timeout and checks elapsed
time on stream events; it is not a hard process-level execution deadline.
Save post-GPU output separately; do not overwrite either CPU baseline.

## Actual measurements

| Metric | CPU result |
| --- | ---: |
| Total stream wall time | 83.9087 s |
| First generated chunk (reasoning) | 33.6017 s |
| First user-visible answer content | Not reached |
| Load time | 30.7595 s |
| Prompt evaluation | 2.4039 s |
| Generation time | 50.6892 s |
| Generated tokens, including reasoning | 256 |
| Generation throughput | 5.0504 tokens/s |
| RAM before, host-wide | 12,296,970,240 bytes / 11.45 GiB |
| Peak sampled RAM, host-wide | 22,526,730,240 bytes / 20.98 GiB |
| RAM after | 22,516,690,944 bytes / 20.97 GiB |
| Average CPU, host-wide | 41.65% |
| Sampling interval / count | 250 ms / 330 |
| Pagefile allocated | 2,048 MiB |
| Pagefile used before / after | 46 / 46 MiB |
| Pagefile peak since boot | 880 MiB; not attributable to this run |
| Resident model allocation after | 10,337,103,379 bytes |
| Resident context | 32,768 |
| GPU allocation | 0 bytes — CPU-only |
| Ollama terminal event | Present; done_reason=length |
| Transport/API error | None reported |
| Final answer | Absent; empty content |

## Interpretation and limitations

**The token budget was exhausted during reasoning.** No final answer/assertion
was produced. This is a valid fixed-budget inference measurement, not a completed
engineering task. Do not label the reasoning chunks as answer content or claim
successful task completion. Do not disable thinking/increase the cap on the GPU
comparison merely to obtain a better-looking result; that would be a different test.

Generation tokens/s excludes load and prompt evaluation. First generated chunk
is not exact token timing. The approximately 30.76-second load dominated much of
the non-generation time; D: I/O and OS cache conditions were not isolated.
Host-wide CPU/RAM includes background apps, the monitor and documentation work;
tests completed before inference. One run and 250 ms samples do not establish
statistical reliability or a precise memory peak. Sampling overhead can vary.

No CPU temperature sensor data or clock/power telemetry was collected. Thermal
throttling is **not determined**, rather than asserted absent. No inference error
or pagefile increase was observed. The prior doctor detected one old GPU-related
log match in a roughly 29-hour-old log; this does not establish a current fault.

## Follow-up stabilization state

- Doctor before inference: 71 PASS / 10 WARN / 0 FAIL.
- Existing suite: 167/167 passed in 37.064s before inference.
- Four containers healthy, six loopback APIs responsive, Tailscale online.
- Original 1.5B baseline and its script, runtime adapters and Compose change preserved.
- No duplicate checkpoint commit; follow-up edits remain reviewable in the working tree.
- Startup unchanged: Tailscale at boot, native tasks after sign-in, Docker manual.
- Software healthy for comparison; driver-installation recovery and physical hardware
  clearance remain incomplete. See `BACKUP_CHECKLIST.md` and `GPU_UPGRADE_PLAN.md`.
