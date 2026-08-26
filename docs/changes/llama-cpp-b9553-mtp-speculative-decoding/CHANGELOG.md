# Changelog: In-Project llama.cpp (b9553) with MTP Speculative Decoding & Author Model Tuning

**Date:** 2026-08-26  
**Status:** Completed  
**Author:** AI Agent (Antigravity)  

---

## 1. Context & Motivation

When testing Multi-Token Prediction (MTP) draft speculative decoding with `gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m` and `gemma-4-12B-it-MTP-Q8_0.gguf` / `gemma-4-12B-it-MTP-F16.gguf` on newer llama.cpp builds (b9702 / b9717), the server crashed with `invalid vector subscript` due to an upstream regression in the `gemma4-assistant` loader path.

The upstream fix / verified baseline is **`llama.cpp b9553` (commit `9e3b928fd`)**, which cleanly loads the MTP draft and provides a **2x+ generation speedup (~88 → ~180 tok/s)** losslessly.

To eliminate external dependencies on LM Studio manual launch and empower Owlynn with native high-throughput local inference, `llama.cpp b9553` was integrated directly into the project repository alongside the author's (`yuxinlu1`) recommended sampling presets.

---

## 2. Key Changes Made

### A. Author-Tuned Sampling Parameters (`src/config/defaults.yaml`)
- Configured sampling defaults recommended by author Yuxin Lu:
  - `top_p: 0.95`
  - `top_k: 64`
  - `repeat_penalty: 1.1`
  - `flash_attention: true` (`-fa on`)
  - `temperature: 0.1` (main workhorse) / `0.2` (pentest mode)
  - `stop`: Complete Gemma stop tokens (`<end_of_turn>`, `<|im_end|>`, `<|endoftext|>`, `<|eot_id|>`, `</s>`, `<|end_of_sentence|>`)

### B. In-Project `llama.cpp` Build Automation (`scripts/setup_llama_cpp.sh`)
- Automated script to clone `llama.cpp` to `./llama.cpp`, checkout verified commit `9e3b928fd` (`b9553`), and compile with Apple Silicon Metal acceleration (`-DGGML_METAL=ON`).
- Added `llama.cpp/` to `.gitignore` to prevent tracking build trees.

### C. High-Throughput Server Launcher (`scripts/run_llama_server.sh`)
- Starts `llama-server` on `http://127.0.0.1:1234/v1` with:
  - Main Model: `gemma4-v2-Q4_K_M.gguf`
  - MTP Draft Model: `gemma-4-12B-it-MTP-F16.gguf` or `gemma-4-12B-it-MTP-Q8_0.gguf`
  - Speculative parameters: `--spec-type draft-mtp --spec-draft-n-max 16 --spec-draft-n-min 1 --spec-draft-p-min 0.75 --spec-draft-ngl auto`
  - Metal & Flash Attention: `-ngl 99 -fa on -fit off`
  - Context window: `-c 16384`
  - Author presets: `--top-p 0.95 --top-k 64 --repeat-penalty 1.1 --jinja --reasoning-format deepseek`
  - Auto-path detection across `~/Documents/LM Studio/`, `/Volumes/KNV3_1TB/LM Studio Model/`, `.models/`, and custom env variables.

### D. Automated Startup Flow (`start.sh` & `setup.sh`)
- **`start.sh`**: Step `[2/3]` now automatically starts `llama-server` in the background when port 1234 is not running, logs to `~/.owlynn/logs/llama_server.log`, waits for health check completion, and terminates it gracefully on `Ctrl+C`.
- **`setup.sh`**: Includes `llama.cpp` compilation in one-time project setup.

### E. Documentation Updates
- Updated [`docs/technical/model-quirks-and-routing.md`](../../technical/model-quirks-and-routing.md) with upstream regression details and b9553 verification.
- Updated [`docs/guides/lm_studio.md`](../../guides/lm_studio.md) with in-project `llama-server` serving instructions and author presets.
- Updated [`docs/guides/dev-startup.md`](../../guides/dev-startup.md) with CMake requirements and new startup workflow.

---

## 3. Verification & Benchmark

- **Binary Version:** `version: 9553 (9e3b928fd)` on AppleClang 21 (Darwin arm64)
- **Speculative Acceptance:** Verified live inference with `draft_n: 190, draft_n_accepted: 111` (58.4% draft acceptance on reasoning).
- **Test Suite:** `pytest tests/test_llm_pool.py tests/test_complex_local_synthesis.py` (11/11 passed).
