# Memory Analysis — May 25, 2026

> **Note**: This document describes historical behavior from the Qwen 3.5 9B fp16 era. The current default medium model is `gemma-4-e4b-uncensored-hauhaucs-aggressive` (Q4_K_M, ~2.5 GB), which uses significantly less memory than the fp16 Qwen variant analyzed here. See [browser-verification.md](browser-verification.md) for the Gemma 4 switch details.

Full memory budget for OwlynnV2 on Mac M4 Air (24 GB unified memory) with local Qwen 3.5 9B via LM Studio + MLX.

---

## System Profile

| Property | Value |
|---|---|
| Hardware | Mac M4 Air |
| Total RAM | 24 GB (unified memory) |
| LLM runtime | LM Studio + MLX |
| Container runtime | Podman (libkrun) |
| Containers | Qdrant, SearxNG, Redis |

---

## Memory Breakdown: Pre-Optimization (Crash State)

At the time of the May 25 segfault crash:

| Consumer | Memory | Notes |
|---|---|---|
| Qwen 3.5 9B weights (fp16) | ~18.0 GB | MLX loads full fp16 weights into unified memory |
| KV cache at 5,280 tokens | ~0.86 GB | Grows with context length; no quantization |
| Podman VM (libkrun) | **1.91 GB** | VM allocation, not container usage |
| └─ Qdrant container | 263 MB | Vector DB |
| └─ SearxNG container | 186 MB | Meta-search engine |
| └─ Redis container | 4 MB | Session/checkpoint store |
| └─ VM idle overhead | ~1.35 GB | Reserved but unused |
| macOS + LM Studio + apps | ~3–4 GB | Window server, browser, terminal, etc. |
| **Total** | **~23.9 GB** | Exceeds 24 GB ceiling at KV cache growth |

**Root cause**: The fp16 model (18 GB) + Podman VM (1.9 GB) + KV cache growth leaves zero headroom on 24 GB. When KV cache expands during generation, `malloc` fails in the MLX C++ runtime — producing a segmentation fault with `<no Python frame>`.

---

## Memory Breakdown: Post-Optimization

After three fixes applied May 25:

| Consumer | Before | After | Delta |
|---|---|---|---|
| Model weights | 18.0 GB | 18.0 GB | — (fp16 unchanged) |
| KV cache (5K tokens) | 0.86 GB | 0.22 GB | **−0.64 GB** (4-bit quant) |
| Podman VM | 1.91 GB | 1.02 GB | **−0.89 GB** |
| macOS + overhead | 3.5 GB | 3.5 GB | — |
| **Total** | **23.9 GB** | **22.4 GB** | **−1.53 GB** |

Headroom: **~1.6 GB** — safe for moderate context growth.

---

## Optimization Applied

### 1. KV Cache Quantization (LM Studio)

```
LM Studio → Model Settings → KV Cache Quantization: 4-bit (Balanced)
```

Reduces KV cache memory ~4x. The "Context Length setting is ignored" message means LM Studio no longer pre-allocates a fixed buffer — the cache grows dynamically with actual token count.

### 2. Podman VM Shrink

```bash
podman machine stop
podman machine set --memory 1024
podman machine start
podman start owlynn_qdrant owlynn_redis owlynn_searxng
```

Reduced from **1907 MB → 1024 MB**. Containers use ~196 MB of the 1024 MB allocation.

**Post-resize container stats:**

| Container | Memory |
|---|---|
| Qdrant | 34 MB |
| SearxNG | 154 MB |
| Redis | 8 MB |
| **Total** | **196 MB** |

### 3. Summarizer Gate (code)

Reduced `_DEFAULT_CONTEXT_WINDOW` in `src/agent/graph.py` from `100_000` → `16_384`. The summarizer now triggers at 85% × 16,384 = ~13,926 tokens, trimming context before KV cache growth becomes dangerous.

---

## Remaining Risk

| Risk | Impact | Mitigation |
|---|---|---|
| fp16 model weights still 18 GB | Minimal headroom on 24 GB | Load Q4_K_M quantized variant (~6 GB) for 12 GB reduction |
| Long conversations with large context | KV cache grows toward limit | Summarizer gate at 13.9K tokens |
| Multiple apps open | macOS memory pressure | Close unnecessary apps before running Owlynn |

---

## How to Check Memory Usage

```bash
# Podman VM allocation
podman machine inspect | python3 -c "import sys,json; d=json.load(sys.stdin)[0]; print(f'Memory: {d[\"Resources\"][\"Memory\"]} MB')"

# Container usage
podman stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}"

# Host memory pressure
vm_stat | head -3 && sysctl hw.memsize | awk '{printf "Total: %.1f GB\n", $2/1024/1024/1024}'

# Check for MLX model memory (while running)
ps aux | grep -i krunkit | grep -v grep | awk '{printf "Podman VM RSS: %.0f MB\n", $6/1024}'
```

---

## Related Documents

- [browser-verification.md](browser-verification.md) — Live browser test results for the 8 bug fixes
- [BUG-ANALYSIS.md](../BUG-ANALYSIS.md) — Root cause analysis of all 8 bugs
- [AGENT_FLOW.md](../AGENT_FLOW.md) — Summarizer gate and context window logic
