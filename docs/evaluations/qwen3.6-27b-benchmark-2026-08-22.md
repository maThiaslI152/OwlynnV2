# Model Benchmark Report: Qwen 3.6 27B Fable Fusion IQ2_M (2026-08-22)

## 1. Model Overview

- **Model Identifier**: `qwen3.6-27b-fable-fusion-711-uncensored-heretic-nm-dau-neo-max-mtp@iq2_m`
- **Architecture**: Qwen 3.5 / 3.6 (27B Dense parameters)
- **Quantization**: IQ2_M (2-bit importance matrix quantization)
- **VRAM / Memory Footprint**: ~10.5 GB
- **Speculative Decoding**: Multi-Token Prediction (MTP) draft tokens enabled
- **Context Length**: 8,192 tokens (Flash Attention enabled)

---

## 2. Benchmark Findings & Performance Metrics

### A. Throughput & Generation Latency
| Metric | Qwen 3.6 27B IQ2_M | Gemma 4 12B Coder Q4 | Gemma 4 26B A4B QAT (MLX) |
|---|---|---|---|
| **Generation Speed** | **~4.1 tok/s** | **41.0 tok/s** | **28.0 tok/s** |
| **Draft Token Acceptance** | **95.5%** (277/290 tokens) | N/A | N/A |
| **Time per Pentest Turn** | **~100s – 140s** | **~2.5s – 4.0s** | **~3.5s – 5.5s** |
| **Reasoning Overhead** | **450 – 1,200 tokens / prompt** | ~50 – 150 tokens | ~80 – 200 tokens |

### B. Quality & Accuracy Analysis
- **Command Generation Precision**: When generation tokens are unconstrained (`max_tokens >= 2048`), the model scored **100%** on target pentest commands (e.g. `nmap -sS --top-ports 1000 -sV`, `nmap -sU`, custom scripts).
- **Reasoning Behavior**:
  - The model performs exhaustive multi-stage reasoning (Role Analysis → Flag Construction → Refinement → Safety checks → Self-correction) before generating response content.
  - **Truncation Vulnerability**: Under standard 512-token caps, the model consumes the entire token budget in the `<think>` block (e.g., 496 reasoning tokens), resulting in empty or truncated output.
  - **Client Timeout Risk**: Because generation speed is ~4.1 tok/s on IQ2_M, prompts generating >500 reasoning tokens + answer take >120s, triggering HTTP client timeouts on standard evaluation harnesses.

---

## 3. Comparative Matrix: Local Models in Owlynn

| Model | Size | Quant | Overall Pentest Quality | Tok/s | Best Role in Owlynn |
|---|---|---|---|---|---|
| **Gemma 4 12B Coder** | 12B | Q4_K_M | **84.1%** | **41 tok/s** | **Dedicated Pentest Model** (Fastest, zero timeouts) |
| **Gemma 4 26B A4B QAT** | 26B | 4-bit MLX | **91.2%** | **28 tok/s** | **Main Local Model** (Router, Extraction, Simple, Local Complex) |
| **Qwen 3.6 27B Fable Fusion** | 27B | IQ2_M | **82.0%** (when unconstrained) | **4.1 tok/s** | **Deep Offline Analysis / Heavy Security Reasoning** |

---

## 4. Recommendations for Heavy 27B Reasoning Models

1. **Context & Budget Allocation**:
   - If using `qwen3.6-27b-fable-fusion-711-uncensored-heretic-nm-dau-neo-max-mtp@iq2_m`, set `max_tokens` to at least `2048` and increase HTTP timeouts to `300s` (`PREDICTION_TIMEOUT_S=300`).
2. **Speculative Decoding**:
   - The MTP draft token mechanism is highly effective (95.5% acceptance rate), boosting raw 2-bit decoding speed.
3. **Production Alignment**:
   - For real-time chat and interactive pentest tooling in Owlynn, `gemma-4-12b-coder` and `gemma-4-26b-a4b-qat` remain superior choices due to 7x–10x higher token velocity with concise execution without timeout risk.
