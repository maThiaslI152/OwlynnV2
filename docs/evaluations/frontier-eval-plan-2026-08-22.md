# Frontier Benchmark Evaluation Plan (2026-08-22)

## 1. Executive Summary & Purpose

The **Frontier Evaluation Benchmark** (`scripts/run_local_frontier_eval.py`) is Owlynn V2's automated end-to-end evaluation suite. It executes a comprehensive 19-turn conversational matrix across a real Playwright browser session connected to the FastAPI backend over WebSockets.

The benchmark systematically tests:
- **Router Precision & Intent Classification**: Validating keyword bypass, heuristic overrides, and the unified local model classifier (`google/gemma-4-26b-a4b-qat`).
- **Deep Multi-Turn Tool Execution**: Multi-step tool chains (`web_search`, `write_workspace_file`, `read_workspace_file`, `fetch_webpage`), Human-In-The-Loop (HITL) approvals, and output compaction.
- **Sustained Reasoning & Codegen**: Frontier-grade architectural reasoning and code generation on DeepSeek V4 (Flash / Pro tiers).
- **Vision Proxy Transcription**: Image intake via the dedicated `baidu.unlimited-ocr` proxy to transcribe visual contexts into text for reasoning without multi-modal model bloat.
- **Hierarchical Memory Subsystem**: Short-term memory (STM), same-thread conversation recall, and cross-thread long-term memory (LTM) retrieval powered by 1024-dimensional `text-embedding-mxbai-embed-large-v1` PostgreSQL `pgvector`.
- **Autonomous File Ingestion & Watcher**: Ingestion pipelines across PDF, DOCX, XLSX, CSV, and background workspace file watchers.
- **Minimal Zero-Emoji UI Observation**: Verification against the 26px bottom `StatusBar`, `ToolActivityCard`, and `HitlPromptCard` timeline components.

---

## 2. Stack & Architecture Baseline

| Subsystem | Active Configuration | Role & Notes |
|-----------|----------------------|--------------|
| **Main Local Model** | `google/gemma-4-26b-a4b-qat` | Consolidated single source of truth for routing, extraction, simple responses, and complex local fallback. |
| **Vision Proxy** | `baidu.unlimited-ocr` | Dedicated vision transcription proxy routing image analysis tasks directly to lightweight text representations. |
| **Pentest Model** | `gemma-4-12b-coder-fable5-composer2.5-v1@q4_k_m` | Dedicated security assessment model for Kali Linux execution and security scenarios. |
| **Cloud Primary** | DeepSeek V4 (`flash` / `pro`) | Cloud complex reasoning with tier escalation and fallback telemetry. |
| **Embeddings** | `text-embedding-mxbai-embed-large-v1` | 1024-dimension embeddings stored in PostgreSQL `vector(1024)` (`memory_vectors`, `engagement_vectors`, `semantic_cache`). |
| **Agent Backbone** | Modular LangGraph | Coordinator (`complex.py`), Prompt Builder (`complex_prompt.py`), Executor (`complex_executor.py`), Tool Action (`complex_tool_action.py`). |
| **UI Design System** | React + Electron (Zero Emoji) | 26px `StatusBar`, flexible Lucide SVG icons, glassmorphism surfaces with CSS custom variables. |

---

## 3. The 19-Turn Frontier Evaluation Matrix

| ID | Category / Topic | Input Prompt | Expected Route | Expected Tools / Events | Key Assertions & Thresholds |
|---|---|---|---|---|---|
| **F1.1** | Router Precision (Simple) | `Hello there! Hope you are doing well today.` | `simple` | `[]` | No tools executed; min 8 chars; keyword bypass bypasses LLM classifier. |
| **F2.1** | Router Precision (Complex) | `Can you review the python code in this function and tell me if it has bugs?` | `complex-cloud` | `[]` | Code-review bypass route to complex; min 40 chars. |
| **F3.1** | Deep Tool Iteration | `Search the web for the weather in Tokyo right now. Then create a file in my workspace named 'tokyo_weather.txt' with the forecast summary.` | `complex-cloud` | `web_search`, `write_workspace_file` | Multi-step tool loop; HITL approval executed; file created in workspace. |
| **F4.1** | Massive Context Ingestion | `Read the file docs/STATUS.md from the workspace. What are the 'Architectural Concerns' listed there?` | `complex-cloud` | `read_workspace_file` | Reads seeded file; accurately extracts architectural concerns; min 40 chars. |
| **F5.1** | Sustained Reasoning | `Write a complete React component for a Data Dashboard... Give me the full code without placeholders.` | `complex-cloud` | `[]` | Complex codegen; min 200 chars; verified streaming without tokenizer deadlock. |
| **F6.1** | Memory Retention (STM) | `Without searching the web again, what city's weather did we look up earlier in this conversation, and what was the exact file name we saved it to?` | `complex-cloud` | `[]` | Asserts exact recall of `tokyo` and `tokyo_weather.txt` from conversation history without tools. |
| **F7.1** | Frontier Quality (Flash) | `Give a rigorous formal proof sketch showing how to optimize this sorting algorithm to best-possible time complexity.` | `complex-cloud` | `[]` | Deep reasoning with `model_tier == flash` (verifies frontier prompts do not silently bump user tier). |
| **F7.2** | Frontier Pro Tier Path | `Summarize the key steps of your previous proof sketch in three bullet points.` | `complex-cloud` | `[]` | Verifies dynamic escalation to `pro` tier when explicitly configured in profile. |
| **F8.1** | Router LLM Classifier | `Over a long career, is breadth or depth usually more valuable? Argue both sides in detail.` | `complex-cloud` | `[]` | Asserts non-bypass classifier source (`classification_source == llm_classifier`) using Gemma 4 26B. |
| **F9.1** | Vision Proxy (OCR) | `What exact text do you see in this image? Reply with the full string only.` (Attached: `ocr_sample.png`) | `complex-cloud` / `vision_cloud` | `[]` | Image transcribed via `baidu.unlimited-ocr`; exact `EVAL_OCR_MARKER` verified in response. |
| **M1.1** | Memory Session Seed | `My project codeword is ZEBRA-42 and we use FastAPI for the backend API layer.` | `complex-cloud` | WS `memory_updated` | Personal memory extraction triggered; fires `memory_updated` event. |
| **M1.2** | Session Memory Recall | `What was my project codeword?` | `complex-cloud` | `[]` | Immediate same-thread recall of `ZEBRA-42` from short-term memory / personal context. |
| **M2.1** | LTM Cross-Thread Recall | `What project codeword did I mention in an earlier conversation?` (New thread) | `complex-cloud` | `[]` | Cross-thread long-term recall from PostgreSQL `memory_vectors` using 1024-dim embeddings. |
| **M4.1** | Memory Retrieval Gate | `Hi there!` | `simple` | No `memory_updated` | Negative assertion: greeting bypasses heavy LTM extraction and vector search. |
| **W1.1** | Autonomous File Watcher | `Read the file eval_watch.txt from my workspace and summarize it in one sentence.` | `complex-cloud` | `read_workspace_file`, WS `file_status` | Disk write detected by background watcher; converted into `.processed/` index; read by agent. |
| **FF1.1** | Format Intake (PDF) | `What marker string appears in the attached PDF? Reply with just that string.` | `complex-cloud` | `[]` | Ingests `sample.pdf` via StirlingPDF / PyMuPDF fallback; asserts marker string `EVAL_PDF_MARKER_55`. |
| **FF2.1** | Format Intake (DOCX) | `What marker string appears in the attached Word document?` | `complex-cloud` | `[]` | Ingests `sample.docx` via `python-docx`; asserts marker string `EVAL_DOCX_MARKER_99`. |
| **FF3.1** | Format Intake (XLSX) | `What value is in col_a of the attached spreadsheet?` | `complex-cloud` | `[]` | Ingests `sample.xlsx` via pandas markdown table; asserts cell marker `EVAL_XLSX_CELL_7`. |
| **FF4.1** | Format Intake (CSV) | `What is the value column for row alpha in the attached CSV?` | `complex-cloud` | `[]` | Ingests `sample.csv` via pandas; asserts row marker `EVAL_CSV_MARKER_42`. |

---

## 4. Scoring Rubric & Quality Gates

Each turn is scored on a **0 to 100** point scale:

| Criterion | Points | Evaluation Mechanism |
|-----------|--------|----------------------|
| **Route Resolution** | +35 to +40 | WebSocket `router_info` metadata matches expected route (tier-aware). |
| **Response Completeness** | +15 to +20 | Non-empty response meeting `min_response_chars` threshold. |
| **Tool Execution Correctness** | +25 to +40 | Authoritative WebSocket `tool_execution` stream contains all expected tools without errors. |
| **Exact Marker / Fact Recall** | +20 | Target codeword, OCR transcription, or document marker present in response body. |
| **Model Tier Adherence** | +15 | Verified `flash` or `pro` tier execution matching runtime configuration. |
| **Classifier Source Verification** | +15 | Verified `llm_classifier` non-bypass execution on open-ended reasoning turns. |
| **WebSocket Lifecycle Events** | +5 each | Receipt of expected async notifications (`memory_updated`, `file_status`). |
| **Format File Processed** | +10 | Background file intake verified in `.processed/` index. |
| **DSML / Markup Leakage** | −15 | Detection of unparsed XML or raw `<tool_call>` tags in user-visible bubble. |
| **Premature Idle / Stall** | −10 | Graph idling before declared tool dependencies execute. |
| **Cloud Fallback Penalty** | **Cap at 49** | Cloud-intended turn unexpectedly falling back to local model during strict cloud evaluation. |

---

## 5. Test Harness Execution & Diagnostic Modes

### Running the Full Frontier Benchmark
```bash
# Auto-detect profile based on active cloud keys and server settings:
PYTHONPATH=. python scripts/run_local_frontier_eval.py --profile auto

# Production-grade Strict Cloud run (fails turns that trigger silent fallback):
PYTHONPATH=. python scripts/run_local_frontier_eval.py --profile cloud --strict-cloud

# Local-only offline benchmark (routes to Gemma 4 26B):
PYTHONPATH=. python scripts/run_local_frontier_eval.py --cloud-off --profile local
```

### Targeted Debugging & Subset Runs
```bash
# Re-run specific failed turns (e.g. Vision Proxy or File Watcher):
PYTHONPATH=. python scripts/run_local_frontier_eval.py --profile cloud --strict-cloud --ids F9.1,W1.1

# Run unit tests for eval scoring harness:
.venv/bin/pytest tests/test_frontier_eval_scoring.py -v
```

### Pre-requisites Checklist
1. Supporting containers active: PostgreSQL (`pgvector`), Redis, Qdrant, StirlingPDF (`./start.sh`).
2. Backend Uvicorn server running on `http://127.0.0.1:8000`.
3. Frontend Vite / Electron server running on `http://127.0.0.1:5173`.
4. LM Studio loaded with `google/gemma-4-26b-a4b-qat` and `baidu.unlimited-ocr`.
5. Valid `DEEPSEEK_API_KEY` set in `.env` for cloud profile turns.
