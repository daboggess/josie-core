# CHAPTER 19: Sequential GPU Swapping and Thermal Stewardship

> *"Two models shall not inhabit the GPU at the same moment. When the generalist yields to the coder, the generalist must depart completely from VRAM before the coder enters. Respect the memory, respect the heat, and the hardware will serve for a decade."*  
> — Josie Runtime Operational Specification, Section 4.3

---

## § 19.1 The Problem of Model Coexistence

In multi-agent architectures, naive systems attempt to load multiple specialized models simultaneously into memory: a router model, a general reasoning model, an embedding model, and a code generation model.

In an 80GB cloud server, such coexistence is trivial. Within Josie’s **12GB hardware invariant**, loading two 8B models (consuming $6	ext{ GB} 	imes 2 = 12	ext{ GB}$) immediately triggers out-of-memory crashes as soon as the first inference request allocates a KV cache.

Project Josie resolved this through the architectural law of **Sequential GPU Swapping**.

```
Time Axis  ------>
Step 1: [ Generalist Loaded: 6.2 GB ] --> Dispatches Task Manifest
Step 2: [ EVICTION: VRAM flushes to 0.4 GB ]
Step 3: [ Coder Loaded: 9.1 GB ]      --> Generates Structured Diff
Step 4: [ EVICTION: VRAM flushes to 0.4 GB ]
Step 5: [ Generalist Reloaded ]       --> Formulates Final User Response
```

---

## § 19.2 The Unload-Before-Load Protocol (`keep_alive=0`)

To guarantee that video memory is fully reclaimed between task transitions, Josie interfaces with the local Ollama daemon using strict eviction parameters.

By default, model runners keep weights cached in VRAM for 5 to 30 minutes to minimize reload latency. In Josie, multi-model workflows explicitly pass `keep_alive: 0` or execute an explicit model unloading call:

```python
def evict_active_model() -> None:
    '''Force immediate unload of any resident model from VRAM.'''
    requests.post(
        "http://127.0.0.1:11434/api/generate",
        json={"model": "", "keep_alive": 0},
        timeout=10
    )
```

The runtime verifies VRAM clearance via NVML (`nvidia-smi`) before loading the next specialized model. If VRAM utilization does not drop below 1,200 MB within 5 seconds of an eviction request, an alert is flagged and garbage collection is forced.

---

## § 19.3 Thermal Dissipation and Cooling Rhythms

Rapid sequential model loading and intensive generation cycles place sustained thermal demands on the GPU silicon. When an LLM generates tokens, CUDA tensor cores operate at maximum electrical draw (170W–220W), generating sudden heat spikes.

Josie’s runtime implements **Thermal Stewardship**:
- **Inter-Task Cooling Pauses:** Between long-running batch inference jobs (such as processing 50 candidate claims), the orchestration loop introduces deliberate 3-to-5 second thermal relaxation intervals.
- **Dynamic Fan Pre-Spinning:** If a high-intensity batch job is queued, fan curves spin up proactively prior to execution, flattening the thermal gradient.
- **Thermal Backoff:** If the GPU core temperature exceeds 75°C, batch inference yields CPU/GPU execution slices until the core cools below 68°C.

This discipline prevents silicon electromigration, extends hardware lifespan, and ensures that the physical rig operates with the quiet, sustained reliability of an industrial machine tool.
