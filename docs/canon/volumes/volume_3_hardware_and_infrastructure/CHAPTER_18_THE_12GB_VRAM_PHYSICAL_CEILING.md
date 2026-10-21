# CHAPTER 18: The 12GB VRAM Physical Ceiling

> *"Twelve gigabytes of video memory is not a limitation; it is our defining architectural anchor. Any system that can only achieve intelligence by consuming 80 gigabytes of datacenter VRAM is a bloated monstrosity. True engineering mastery is extracting frontier capability from a 12GB ceiling."*  
> — Dustin, Hardware Invariants Directive (`DEC-0021`)

---

## § 18.1 The 12GB Hardware Invariant

Modern AI research operates under the lazy assumption of infinite compute. Frontier models are trained on clusters of tens of thousands of NVIDIA H100s, and standard open-weights deployments casually assume 24GB (RTX 4090/3090) or 80GB (A100/H100) VRAM envelopes.

Project Josie established an immutable physical baseline in **Decision `DEC-0021`**:
**The system shall operate within a hard, single-GPU physical limit of 12GB VRAM (NVIDIA GeForce RTX 3060 12GB / RTX 4070 12GB class).**

This constraint was not chosen out of poverty; it was chosen out of **stewardship and democratization**. A system that requires a $30,000 enterprise GPU can never be sovereignly owned by a small business, a craftsman, a shop, or a household. By binding Josie's architecture to the 12GB VRAM ceiling, Dustin ensured that Josie represents a truly replicable, local, low-power cognitive architecture.

---

## § 18.2 Memory Budgeting: The VRAM Anatomy

Within a 12GB (12,288 MB) physical ceiling, video memory must be allocated with surgical precision. VRAM is not merely occupied by model weights; it must accommodate the KV cache (key-value attention cache), compute activation buffers, and operating system display overhead.

```
+-----------------------------------------------------------------------+
|                       12,288 MB TOTAL VRAM BUDGET                     |
+------------------------------------+------------------+---------------+
| Model Weights (Quantized Q4/Q5)    | KV Context Cache | Headroom / OS |
| 7B @ Q5_K_M (~5.5 GB)              | 8K - 16K Context | Scratchpad    |
| 14B @ Q4_K_M (~9.2 GB)             | (~1.8 - 2.4 GB)  | (~1.0 GB)     |
+------------------------------------+------------------+---------------+
```

The mathematical budget enforces strict boundaries:
$$	ext{VRAM}_{	ext{total}} = 	ext{Weights}_{	ext{quantized}} + 	ext{KV\_Cache}(L, H, B, C_{	ext{ctx}}) + 	ext{Activation\_Buffer} + 	ext{OS\_Overhead} \le 11,500	ext{ MB}$$

Where:
- $L$ = Number of transformer layers
- $H$ = Hidden dimension size
- $B$ = Batch size (fixed strictly at $B=1$ for local single-user execution)
- $C_{	ext{ctx}}$ = Context window length (typically 8,192 or 16,384 tokens)

A reserve buffer of at least 788 MB is unconditionally preserved to prevent catastrophic Out-Of-Memory (`CUDA: out of memory`) kernel panics.

---

## § 18.3 Quantization Mastery: GGUF, Q4_K_M, and Q5_K_M

To execute sophisticated 7-billion to 14-billion parameter models within 12GB of VRAM, precision must be quantized without sacrificing semantic reasoning capability.

Extensive empirical testing within Project Josie demonstrated the efficacy of modern GGUF quantization formats:
1. **FP16 (Half Precision - 16 bits per parameter):** Completely unfeasible. A 14B model requires ~28GB VRAM; even an 8B model requires ~16GB, instantly breaching the 12GB ceiling.
2. **Q8_0 (8 bits per parameter):** Near-zero perplexity loss, but a 14B model consumes ~15GB. Viable only for compact 3B–7B models.
3. **Q5_K_M (5-bit K-quant medium):** The "sweet spot" for 7B–9B generalist models. Delivers 99.4% of FP16 reasoning accuracy while fitting comfortably within ~5.8GB to ~6.4GB of VRAM, leaving ample room for 16K context buffers.
4. **Q4_K_M (4-bit K-quant medium):** The necessary format for 14B parameter models (such as Qwen 2.5 14B Coder). Weights occupy ~9.1GB, allowing an 8,192 token context window while hugging the 11.2GB utilization ceiling.

---

## § 18.4 Context Window Constraints and Context Budgeting

VRAM consumption grows linearly with context length. In naive implementations, developers casually pass 64,000 or 128,000 tokens into local models, only to watch the KV cache consume 15GB of VRAM and crash the process.

Under Josie’s memory governance:
- **Default Context Window:** Clamped to **8,192 tokens** for standard operational tasks.
- **Extended Context Window:** Clamped to **16,384 tokens** only for specialized coding audits, with automatic KV cache quantization (`q8_0` or `q4_0` KV cache enabled in Ollama/llama.cpp).
- **Fail-Closed Context Truncation:** The `KnowledgePrimingCompiler` calculates the exact token budget of canonical claims before issuing the prompt. If the bundle exceeds the safe token envelope, the compilation fails closed before invoking the GPU.
