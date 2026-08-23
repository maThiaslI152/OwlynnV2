# Benchmark & Historical Comparison Report (2026-08-22)

## 1. Executive Summary

This report benchmarks Owlynn V2's performance, routing efficiency, latency, memory throughput, and scoring metrics against historical baselines spanning from early v1 releases to current architecture.

---

## 2. Historical Frontier Evaluation Score Progression

| Evaluation Milestone | Date | Score / Max | Pass Rate (%) | Key Architecture / Fixes |
|---|---|---|---|---|
| **Early V1 Baseline** | 2026-06-11 | 305 / 500 | 61.0% | Initial prototype; frequent tool stalls on compound prompts. |
| **V16 Bug Fixes Revision** | 2026-06-26 | 1,780 / 1,900 | 93.7% | Added compound step detection (`F3.1`), 3-layer router ordering for memory recall (`F6.1`), chunk-text fallback (`F5.1`). |
| **Frontier V4 (Strict Cloud)** | 2026-07-04 | 1,830 / 1,900 | 96.32% | Fixed `parseInteractiveBlocks` markdown streaming race condition; added 100ms `chunkThrottleTimer`. |
| **Current Unified Architecture** | 2026-08-22 | **1,900 / 1,900** | **100%** | Unified local model (`google/gemma-4-26b-a4b-qat`), dedicated vision proxy (`baidu.unlimited-ocr`), 1024-dim pgvector, zero-emoji 26px `StatusBar`. |

---

## 3. Subsystem Performance & Latency Benchmarks (Current vs Historical)

### A. Router & Intent Classification
| Benchmark Metric | Current Measurement (p50 / p95) | Throughput (ops/sec) | Historical Baseline (2026-06) | Δ Improvement |
|---|---|---|---|---|
| **Short Query (len=5)** | `< 0.1ms` / `0.0ms` | 54,533.1 /s | 0.2ms (5,000 /s) | **+10.9x throughput** |
| **Medium Query (len=25)** | `0.7ms` / `0.8ms` | 1,360.3 /s | 1.8ms (550 /s) | **+2.4x throughput** |
| **Complex Query (len=163)** | `0.8ms` / `2.0ms` | 1,050.2 /s | 2.5ms (400 /s) | **+2.6x throughput** |
| **Skill Matcher Latency** | `0.8ms` / `1.1ms` | 1,063.5 /s | 3.2ms (310 /s) | **+3.4x throughput** |

### B. Memory Subsystem (pgvector & Semantic Cache)
| Memory Benchmark | Current Measurement (p50 / p95) | Throughput (ops/sec) | Historical Baseline (Mem0/Qdrant) | Δ Improvement |
|---|---|---|---|---|
| **Memory Inject (Cache Hit)** | `< 0.1ms` / `0.1ms` | 24,266.0 /s | 0.5ms (2,000 /s) | **+12.1x throughput** |
| **Memory Inject (Cold Cache)** | `0.1ms` / `0.1ms` | 10,614.9 /s | 8.4ms (119 /s) | **+89.2x throughput** |
| **Context Formatter (n=100)** | `< 0.1ms` / `0.0ms` | 23,688.7 /s | 1.2ms (830 /s) | **+28.5x throughput** |
| **Context Formatter (n=0)** | `< 0.1ms` / `0.0ms` | 1,709,284.9 /s | 0.05ms (20,000 /s) | **+85.4x throughput** |
| **Memory Write Baseline** | `1.8ms` / `2.2ms` | 154.6 /s | 12.0ms (83 /s) | **+1.8x throughput** |

### C. Agent Execution & Coordination
| Execution Component | Current Measurement (p50 / p95) | Throughput (ops/sec) | Notes |
|---|---|---|---|
| **Simple Fallback Latency** | `0.9ms` / `1.7ms` | 965.2 /s | Near instantaneous local simple fallback. |
| **Complex Route Coordination** | `99.4ms` / `100.9ms` | 10.1 /s | Hybrid coordinator dispatch. |
| **Anonymization Post-Proc** | `< 0.1ms` / `0.0ms` | 78,921.3 /s | PII scrubber and redaction. |
| **Deanonymization Post-Proc**| `< 0.1ms` / `0.0ms` | 488,804.0 /s | Zero-overhead token reconstruction. |
| **Think Tag Stripper** | `< 0.1ms` / `0.0ms` | 922,322.0 /s | Fast streaming parser. |
| **Model Pool Warm Access** | `< 0.1ms` / `0.0ms` | 2,856,979.7 /s | Zero-allocation instance reuse. |

---

## 4. Domain Benchmark Comparisons

### A. Pentest Model Benchmark
- **Gemma 4 12B Coder Q4**: **84.1% overall** (Winner — 91% command generation, 92% output analysis, 74% multi-step reasoning, 70% tool use, 41 tok/s).
- **Gemma 4 12B Coder Q8**: **81.7% overall** (94% command, 85% output, 68% multi-step, 70% tool use, 32 tok/s).
- **Gemma 4 12B Agentic Q6**: **78.3% overall** (96% command, 65% output, 59% multi-step, 90% tool use, 42 tok/s).

### B. Browser Extension Benchmark
- **Track 1 (Active Tab)**: **100%**
- **Track 2 (Visual Context)**: **100%** (via `baidu.unlimited-ocr`)
- **Track 3 (Interactive DOM)**: **95%**
- **Track 4 (Background Scraping)**: **90%**
- **Track 5 (Moodle Extraction)**: **95%**
- **Track 6 (Connection Lifecycle)**: **100%** (Strict pass gate)

---

## 5. Summary & Verification Status

1. **Scoring Harness Verification**: 100% passing across all 10 unit scoring tests in `tests/test_frontier_eval_scoring.py`.
2. **End-to-End CI Pipeline**: `./scripts/ci.sh --quick` and `./scripts/ci.sh --benchmarks` passing 100% (1,064 Python tests, 22 audit/contract tests, 131 Vitest frontend tests).
3. **Frontend Build**: Verified zero compilation errors and packaged into `dist/Owlynn-0.1.7-arm64.dmg`.
