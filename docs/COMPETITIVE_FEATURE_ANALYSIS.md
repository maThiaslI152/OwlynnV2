---
status: active
category: reference
last_updated: 2026-06-07
owner: human
---

# Competitive Feature Gap Analysis — Owlynn vs. Leading Local AI Assistants

> **Purpose:** Competitive feature gap analysis — Owlynn vs. leading local AI assistants.

**Date:** 2026-05-22 (original) · **Revised:** 2026-06-07  
**Audience:** Owlynn maintainers, AI agents planning feature work  
**Context:** Feature comparison of Owlynn against Open WebUI, AnythingLLM, Jan, LM Studio, and GPT4All

> **Revision note (2026-06-07):** Updated architecture recap, routing, models, cloud tier, and feature status to match DeepSeek V4 Phases 0–4, Electron desktop, 3-way routing, removed SwapManager, OpenAI-compatible API + CLI, image upload, Docling parsing, and Knowledge Cache. Gap analysis recommendations adjusted accordingly.

---

## 1. Executive Summary

Owlynn has carved a unique niche as a **local-first AI desktop agent with a sophisticated hybrid model routing architecture, security proxy, and LangGraph orchestration** — none of the five competitors combine all of these. However, significant gaps exist in **programmatic access, model management UX, document RAG, and tool extensibility**. The highest-impact opportunities are features that build on existing strengths without requiring architectural overhauls.

**Top 3 recommendations (updated 2026-06-07):**

1. **LocalDocs-style workspace file indexing (Automatic Document RAG)** — Medium effort, fills biggest remaining UX gap (GPT4All parity). Knowledge Cache covers conversation facts, not folder-wide doc search.
2. **Extension/plugin system for tools** — Medium effort, leverages MCP foundation (Open WebUI/Jan parity)
3. **In-app model browser / hub** — Medium effort; config is centralized in `defaults.yaml` but discovery still requires LM Studio

*Previously top priority:* OpenAI-compatible local API + CLI — **now implemented** (see §3.1); polish HITL/API-mode behavior remains.

---

## 2. Owlynn Current Architecture Recap

Before comparing, here is what Owlynn already has (see [`architecture/overview.md`](architecture/overview.md), [`CLOUD-LLM-ARCHITECTURE.md`](CLOUD-LLM-ARCHITECTURE.md), [`architecture/DEEPSEEK_V4_INTEGRATION.md`](architecture/DEEPSEEK_V4_INTEGRATION.md)):

| Capability | Implementation |
|---|---|
| Desktop shell | **Electron** (macOS `.app` / `.dmg` via `frontend-v2`); legacy Tauri CSS classes remain in stylesheet only |
| Agent orchestration | LangGraph graph: `memory_inject → router → complex_llm ↔ security_proxy ↔ tool_action → memory_write` |
| Model routing | **Cloud-primary:** `simple` (MiniCPM5-1B) or `complex-cloud` (DeepSeek V4). Extraction: Gemma 4 E2B (local, background, shares models.small). Legacy `complex-default`/`complex-vision`/`complex-longctx` and **SwapManager** removed (2026-06) |
| Cloud path | `prepare_cloud_payload()` — PII anonymization, brief gate, stable/volatile prompt layers, vision proxy, prefix cache metrics. Phase 5 **output** cache deferred |
| Tools | 20+ built-in tools + skill chains (`.md` in `skills/`) + MCP STDIO |
| Security | `security_proxy` HITL on sensitive tools, HMAC audit trail, cloud anonymization |
| Memory | Three-tier: JSON STM, Mem0+Qdrant LTM (**nomic-embed-text-v1.5**, 768-dim), topic/interest extraction. **Knowledge Cache** for fast factual recall (see [`architecture/KNOWLEDGE_CACHE.md`](architecture/KNOWLEDGE_CACHE.md)) |
| Document parsing | **Docling** in `file_processor.py` for PDF/DOCX/PPTX → markdown; workspace file tools; not full auto-folder RAG |
| Context management | Auto-summarization at ~85% tokens; multi-level compression |
| Frontend | React 19 + TypeScript, Vite, Zustand, WebSocket streaming; composer supports drag-and-drop files/images |
| Programmatic access | `POST /v1/chat/completions` on port **8000** ([`openai.py`](../src/api/routes/openai.py)); CLI via [`src/cli.py`](../src/cli.py) |
| Voice | `speak_text` TTS (macOS `say`); Live Talk removed |
| Test coverage | ~934 Python + 103 frontend tests; property-based + contract suites |
| CI/CD | Local CI via `scripts/ci.sh`, pre-push hook |

**Cloud tier rationale:** DeepSeek V4 flash is the default cloud workhorse because of (1) **cost** — ~$0.14/M input tokens, ~$0.014/M cache hits, ~$0.28/M output (flash tier in `defaults.yaml`); (2) **context** — 1M token window; (3) **safety** — all cloud traffic anonymized before leaving the machine. Pro tier available for higher reasoning quality at higher cost.

---

## 3. Feature-by-Feature Comparison

### 3.1 Programmatic Access & APIs

#### 3.1.1 OpenAI-Compatible Local API Server

| | |
|---|---|
| **Who has it** | Jan (localhost:1337), LM Studio (localhost:1234, consumed internally) |
| **Owlynn status** | **Implemented (basic).** `POST /v1/chat/completions` on `127.0.0.1:8000` routes through LangGraph ([`src/api/routes/openai.py`](../src/api/routes/openai.py)). Supports streaming SSE and `project_id` / `auto_approve_sensitive` flags. WebSocket remains the primary GUI path. |
| **Remaining gaps** | No dedicated port 1337/8001 alias; HITL behavior in API mode still evolving; not all WS features exposed (router metadata, cache stats). |
| **Effort** | Quick Win polish (2–4 hours) — docs, auth token, parity with WS modes |
| **Impact** | **High.** Enables scripting, IDE integration (VS Code/Cursor extension), CI/CD pipelines, and headless operation. Opens Owlynn to automation use cases without the GUI. |
| **Technical approach** | Add a `/v1/chat/completions` endpoint to FastAPI that routes through the LangGraph graph with a `mode: "api"` flag. The endpoint would accept standard OpenAI-compatible JSON, execute the full agent flow (routing → tool loop → memory), and stream back SSE or return a complete response. Key considerations: |
|  | - Authenticate via localhost-only binding or a local API key (file-based token) |
|  | - Disable HITL interrupts in API mode (auto-approve all safe tools, reject sensitive ones with error) |
|  | - Skip the `action_proposal_queue` flow — all tool calls either auto-execute or return `requires_approval` |
|  | - Match Jan's convention: listen on `127.0.0.1:1337` (Owlynn's own port) or `127.0.0.1:8001` to avoid conflicts |
|  | - Use `sse-starlette` for streaming responses (FastAPI-compatible SSE) |

#### 3.1.2 CLI Tool

| | |
|---|---|
| **Who has it** | LM Studio (`lms` CLI), GPT4All (Python bindings) |
| **Owlynn status** | **Implemented (basic).** [`src/cli.py`](../src/cli.py) with `query`, `stream`, and `status` commands targeting `/v1/chat/completions`. Run: `python src/cli.py query "Hello"`. |
| **Remaining gaps** | No packaged `owlynn` shell shim; no `owlynn serve` auto-start. |
| **Effort** | Quick Win polish (1–2 hours) |
| **Impact** | **Medium.** Convenience for power users. Enables `owlynn "summarize this file"` from terminal. |
| **Technical approach** | A Python CLI via `click` or `typer` that sends requests to the local API server (from §3.1.1). Wrap as `scripts/owlynn` shell script. Options: |
|  | - `owlynn chat "question"` — single-turn query |
|  | - `owlynn file analyze path/to/file` — send file content to agent |
|  | - `owlynn --stream "question"` — streaming response |
|  | - `owlynn serve` — check if API server is running, start if not |
|  | - This is trivial once the API server exists. Implement as a thin client over the OpenAI-compatible endpoint. |

#### 3.1.3 Python/TypeScript SDK

| | |
|---|---|
| **Who has it** | LM Studio (TS/Python), GPT4All (Python) |
| **Owlynn status** | No SDK. All integration requires understanding the WebSocket protocol. |
| **Effort** | Medium (2–4 days) |
| **Impact** | **Medium.** Enables programmatic agent composition. Lower priority than the local API server since the OpenAI-compatible endpoint serves as a universal SDK interface. |
| **Technical approach** | Publish `owlynn-sdk` Python package that wraps the local API server with convenience methods: |
|  | - `OwlynnClient.chat("question")` → response stream |
|  | - `OwlynnClient.tools.list()` → tool metadata |
|  | - `OwlynnClient.memory.search("query")` → semantic results |
|  | - Could reuse `openai` Python package with `base_url="http://127.0.0.1:8001/v1"` as the simplest approach |

---

### 3.2 Model Management & Discovery

#### 3.2.1 In-App Model Browser / Hub

| | |
|---|---|
| **Who has it** | LM Studio (built-in HuggingFace browser), Jan (model hub with HF integration), GPT4All (curated model gallery) |
| **Owlynn status** | Depends on LM Studio for load/unload. Model names and endpoints live in **`src/config/defaults.yaml`** (override via `.env`, `.env.local`, Settings UI). No in-app HF browser. SwapManager removed — single medium model handles complex + vision. |
| **Effort** | Medium (3–5 days) |
| **Impact** | **High.** Major UX improvement. Currently, users must leave Owlynn to manage models, breaking the single-app experience. |
| **Technical approach** | Since Owlynn uses LM Studio on port 1234, extend the model management UI to: |
|  | 1. **List loaded models** — `GET /v1/models` from LM Studio |
|  | 2. **List available/downloaded models** — LM Studio local model directory |
|  | 3. **HuggingFace search** — HF API for MLX-compatible models with VRAM estimates |
|  | 4. **One-click configure** — Map models to `models.small` / `models.cloud` in Settings, persist to profile overrides |
|  | 5. **Model card view** — Size, context window, quantization, HF link |
|  | **Caveat:** Actual download still happens via LM Studio or `huggingface-cli`. Owlynn's role is discovery + configuration. Full one-click download requires LM Studio to support it via API (currently it doesn't). |

#### 3.2.2 Chat Format Templates / Presets

| | |
|---|---|
| **Who has it** | LM Studio (chat format presets for different model families) |
| **Owlynn status** | Hardcoded prompts in `simple.py` and `complex.py`. No per-model prompt template configuration. The `lm_studio_fold_system` advanced setting partially addresses this but isn't user-facing. |
| **Effort** | Quick Win (2–3 hours) |
| **Impact** | **Medium.** Reduces friction when switching models (different models need different system prompt formats). |
| **Technical approach** | Add a `chat_templates` section to `user_profile.json` or advanced settings: |
|  | ```json |
|  | { |
|  |   "chat_templates": { |
|  |     "qwen3.5": { "system_prefix": "...", ... }, |
|  |     "llama-3": { "system_prefix": "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n", ... } |
|  |   } |
|  | } |
|  | ``` |
|  | Expose in frontend as a dropdown on the model configuration panel. Default to LM Studio's detected template. |

#### 3.2.3 Model Performance Benchmarking

| | |
|---|---|
| **Who has it** | LM Studio |
| **Owlynn status** | No benchmarking. Performance is only tracked per-SLO (latency targets in `docs/PERFORMANCE_SLOS.md`). |
| **Effort** | Medium (2–3 days) |
| **Impact** | **Low-Medium.** Useful for power users evaluating models, but not essential for day-to-day use. Can be deferred. |
| **Technical approach** | Add a `/api/models/benchmark` endpoint that runs a standard prompt suite (coding, reasoning, summarization) through each configured model and reports: |
|  | - Tokens/second (prompt eval + generation) |
|  | - Time to first token |
|  | - VRAM usage (via LM Studio API) |
|  | - Token quality metrics (basic checks) |
|  | Store results in `data/benchmarks.json` for comparison over time. |

---

### 3.3 Document Processing & RAG

#### 3.3.1 Automatic Document Indexing (LocalDocs-style RAG)

| | |
|---|---|
| **Who has it** | GPT4All (LocalDocs — zero-config file indexing), Open WebUI (9 vector DBs for RAG), AnythingLLM (data connectors) |
| **Owlynn status** | **Partial.** Workspace file tools, Docling parsing (`file_processor.py`), PDF cache in `.processed/`, and **Knowledge Cache** (conversation-derived facts in Qdrant — see [`KNOWLEDGE_CACHE.md`](architecture/KNOWLEDGE_CACHE.md)) exist. **No** automatic folder watch or chunk-indexed document RAG like GPT4All LocalDocs. `ProjectKnowledgePanel` lists project-attached knowledge files but does not embed entire workspace trees. |
| **Effort** | Medium (3–5 days) for full LocalDocs parity |
| **Impact** | **Very High.** This is the single biggest UX gap. GPT4All's killer feature is "drop a folder and ask questions about it." Owlynn already has Qdrant running — the infrastructure exists. |
| **Technical approach** | Build a document indexing pipeline that uses Owlynn's existing Qdrant instance: |
|  | 1. **Watch folders** — Monitor workspace directories for new/changed files (use `watchfiles` Python package) |
|  | 2. **Parse documents** — Support PDF (PyMuPDF, already used), .docx (python-docx), .md, .txt, .py, .ts, .tsx, .json |
|  | 3. **Chunk** — Use `langchain.text_splitter.RecursiveCharacterTextSplitter` with overlap |
|  | 4. **Embed** — Use Owlynn's existing embedding model (`text-embedding-nomic-embed-text-v1.5-embedding` via LM Studio) |
|  | 5. **Store** — Index chunks in Qdrant under a separate collection `workspace_docs` keyed by `(project_id, file_path, chunk_index)` |
|  | 6. **Query** — Add a `search_workspace_docs` tool that performs hybrid search (semantic + keyword) over indexed documents |
|  | 7. **UI** — Add a file list with indexing status (indexed/indexing/pending) in the workspace panel |
|  | **Memory budget:** Indexing 1000 documents × ~200 chunks each × 384-dim embeddings ≈ ~300 MB in Qdrant. Within Owlynn's ~200 MB Qdrant budget if limited to current project. |

#### 3.3.2 Content Extraction Engines (OCR, Advanced Parsing)

| | |
|---|---|
| **Who has it** | Open WebUI (Tika, Docling, Mistral OCR) |
| **Owlynn status** | **Partial.** Docling integrated for PDF/DOCX/PPTX in [`file_processor.py`](../src/api/file_processor.py). PyMuPDF fallback paths remain. No standalone `parse_document` agent tool; OCR via Docling/EasyOCR on ingest. Scanned PDF quality varies. |
| **Effort** | Quick Win (expose parsed markdown as tool) to Medium (full pipeline integration) |
| **Impact** | **Medium.** Enables processing of scanned documents, screenshots, and complex formats. Complements the document indexing feature above. |
| **Technical approach** | Docling is already a dependency. Next steps: |
|  | - Expose `parse_document` as an agent tool wrapping existing `file_processor` |
|  | - Feed Docling markdown into the §3.3.1 indexing pipeline when built |
|  | - Defer Mistral OCR (cloud-only; conflicts with local-first unless opt-in) |

---

### 3.4 Tool Extensibility & Plugins

#### 3.4.1 Extension / Plugin System

| | |
|---|---|
| **Who has it** | Open WebUI (plugin marketplace, Pipelines framework), Jan (extension system), AnythingLLM (agent skills marketplace) |
| **Owlynn status** | 20+ built-in tools, skill chains (`.md` in `skills/`), and MCP STDIO. However: |
|  | - Skills are prompt templates, not code — they can't add new capabilities |
|  | - MCP STDIO is the closest to an extension mechanism but requires running separate servers |
|  | - No marketplace or community contribution model |
|  | - Adding a new tool requires modifying `src/tools/`, `src/agent/tool_sets.py`, and `complex.py` |
| **Effort** | Medium (4–7 days) |
| **Impact** | **High.** Enables community contributions and user customization without core code changes. Leverages Owlynn's security proxy (extensions go through the same HITL approval). |
| **Technical approach** | Build on Owlynn's existing MCP foundation. Instead of building a custom plugin format, adopt MCP as the universal extension protocol: |
|  | 1. **MCP Server Discovery** — Scan a `~/.owlynn/mcp/` directory or a configured list for MCP server manifests |
|  | 2. **One-Click MCP Install** — UI to add MCP servers from a registry or URL, storing config in `mcp_config.json` |
|  | 3. **Local Plugin Format** — For the simplest tools, support a `~/.owlynn/plugins/<name>/plugin.json` + `tool.py` format that auto-registers LangChain `@tool` functions |
|  | 4. **Sandbox** — Run user plugins in a subprocess with restricted filesystem access (only the plugin's own directory + designated workspace). Use `subprocess` + JSON-RPC over stdin/stdout. |
|  | 5. **Security** — All plugin tool calls go through the existing `security_proxy`. New plugin tools default to `SENSITIVE` (require approval). Users can mark trusted plugins as safe. |
|  | 6. **Marketplace (future)** — A curated list on GitHub. Owlynn fetches the index and displays available plugins in-app. Not a priority for solo dev. |

#### 3.4.2 Tool Pipelines (Compute Offloading)

| | |
|---|---|
| **Who has it** | Open WebUI (Pipelines plugin framework) |
| **Owlynn status** | All computation runs in-process. Large tasks (e.g., batch document processing) block the agent loop. |
| **Effort** | Major (2–3 weeks) |
| **Impact** | **Low-Medium.** Useful for batch workloads but premature for a solo-dev personal assistant. |
| **Technical approach** | Queue-based pipeline system using Redis streams (already have Redis): |
|  | - Submit long-running tasks to a `owlynn:pipelines` stream |
|  | - Worker processes consume tasks, report progress via Redis |
|  | - Agent polls for results or receives notifications |
|  | - **Defer** until there's clear demand. The existing async tool execution is sufficient for most use cases. |

---

### 3.5 Multi-Modal & Voice

#### 3.5.1 Voice Input (Whisper/STT)

| | |
|---|---|
| **Who has it** | Open WebUI (Whisper integration), AnythingLLM (multi-modal including audio) |
| **Owlynn status** | Only `speak_text` TTS (macOS `say`). Live Talk (wake-word + STT) was removed in April 2026 due to complexity and instability (ObjC FFI crashes, TTS feedback loops, macOS permission issues). |
| **Effort** | Medium (2–4 days for basic Whisper; Major for full Live Talk revival) |
| **Impact** | **Medium.** Voice input is nice-to-have, not essential. The previous Live Talk attempt was a significant time sink. A simpler approach is warranted. |
| **Technical approach** | **Simpler than Live Talk:** Instead of continuous wake-word listening, implement a push-to-talk button that records audio and transcribes via Whisper: |
|  | 1. **Frontend:** Add a mic button in the composer. On press, record via `navigator.mediaDevices.getUserMedia()` + `MediaRecorder` API. Send WAV/WebM to backend. |
|  | 2. **Backend:** `POST /api/transcribe` endpoint. Use `faster-whisper` (CTranslate2, optimized for Apple Silicon) with a small model (`tiny.en` or `base.en`, <200 MB). Runs entirely locally. |
|  | 3. **Flow:** Record → transcribe → insert transcription into composer → user edits and sends. Not auto-send. |
|  | 4. **Avoid** continuous listening, wake-words, and ObjC FFI. This is a 10x simpler feature that delivers 80% of the value. |

#### 3.5.2 Multi-Modal Input (Images, Audio Files)

| | |
|---|---|
| **Who has it** | AnythingLLM |
| **Owlynn status** | **Implemented (images).** Composer drag-and-drop + attachment chips ([`Composer.tsx`](../frontend-v2/src/components/Composer.tsx)). Router sends images to `complex-cloud` (Gemma 4 E2B vision proxy → DeepSeek text). No audio file ingestion. |
| **Effort** | Done for images; Medium for audio (1–2 days) |
| **Impact** | **Medium.** Image support exists but upload UX could be polished. Audio file analysis (e.g., "summarize this meeting recording") is a differentiator. |
| **Technical approach** | 1. **Image upload:** ✅ Drag-and-drop in composer; base64 `image_url` to backend. |
|  | 2. **Audio file:** Transcribe via Whisper pipeline from §3.5.1, then feed transcription into agent. |

---

### 3.6 Conversational & Organizational Features

#### 3.6.1 Thread/Conversation Organization

| | |
|---|---|
| **Who has it** | Jan (thread organization) |
| **Owlynn status** | Projects have multiple chats. Basic CRUD via `GET/POST/DELETE /api/projects/{id}/chats`. No folders, tags, pinning, search across conversations. |
| **Effort** | Medium (2–3 days) |
| **Impact** | **Medium.** Becomes important as conversation history grows. Jan's thread view is a model to follow. |
| **Technical approach** | 1. **Chat search** — Add `GET /api/chats/search?q=<term>` that searches conversation titles and message content via Redis or a lightweight full-text index |
|  | 2. **Pinned chats** — Add `pinned` boolean to chat metadata, sort pinned to top |
|  | 3. **Tags/Labels** — Add optional `tags: string[]` to chat metadata. Filter by tag in sidebar. |
|  | 4. **Date grouping** — Group chats by Today, Yesterday, This Week, Older in sidebar |

#### 3.6.2 Custom Agent / Persona Builder

| | |
|---|---|
| **Who has it** | AnythingLLM (custom AI agents builder), Open WebUI (model builder, community characters) |
| **Owlynn status** | Single persona configured via `system_prompt` + `custom_instructions` + `tone` in system settings. Skills are prompt templates. No way to create distinct agent personalities or multi-agent setups. |
| **Effort** | Medium (3–5 days) |
| **Impact** | **High.** Enables specialized workflows: coding agent with different tools, writing assistant with specific tone, research agent with web focus. |
| **Technical approach** | Extend the skills system into "agent personas" — a persona is a curated skill + system prompt + tool set: |
|  | 1. **Persona definition** — `~/.owlynn/personas/<name>.json`: |
|  |   ```json |
|  |   { |
|  |     "name": "Code Reviewer", |
|  |     "system_prompt": "You are an expert code reviewer...", |
|  |     "tone": "precise", |
|  |     "toolbox": ["file_ops"], |
|  |     "default_model": "medium", |
|  |     "web_search_enabled": false, |
|  |     "temperature": 0.2 |
|  |   } |
|  |   ``` |
|  | 2. **Persona selector** — Dropdown in composer to switch personas. Switching changes system prompt, tool set, and model preference. |
|  | 3. **Chat association** — Each chat thread is associated with a persona. Switching mid-conversation is possible. |
|  | 4. **Built-in personas** — Ship 3–5 defaults: General Assistant, Code Helper, Writing Coach, Research Assistant, Meeting Notetaker |
|  | 5. **Per-persona memory** — Optionally scope long-term memory to a persona (use `persona_id` as part of the Mem0 filter) |

---

### 3.7 Web Search & Connectivity

#### 3.7.1 More Web Search Providers

| | |
|---|---|
| **Who has it** | Open WebUI (15+ providers) |
| **Owlynn status** | 5 tiers: wttr.in (weather), SearXNG (self-hosted), Brave/Serper/Tavily APIs, curl_cffi scraping, Playwright. |
| **Effort** | Quick Win (1–2 hours per provider) |
| **Impact** | **Low.** Owlynn's current search pipeline is already robust. Adding providers is marginal improvement. |
| **Technical approach** | Prioritize the ones that add genuinely new capabilities: |
|  | - **Exa/Metaphor** — Neural search for high-quality results (requires API key) |
|  | - **Kagi** — Privacy-respecting paid search (requires API key) |
|  | - Low priority; current SearXNG + DDG fallback is sufficient for most users |

#### 3.7.2 Data Connectors (External Services)

| | |
|---|---|
| **Who has it** | AnythingLLM (Slack, GitHub, Confluence, etc.) |
| **Owlynn status** | No external service connectors. All data is local files. |
| **Effort** | Major (2–4 weeks for a connector framework + initial connectors) |
| **Impact** | **Low-Medium.** Conflicts with local-first philosophy. Each connector is a maintenance burden. |
| **Technical approach** | **Defer.** This is scope creep for a solo dev. If needed, implement as MCP servers (e.g., `@modelcontextprotocol/server-github`) rather than built-in connectors. Owlynn's MCP client already supports this pattern. |

---

### 3.8 Multi-User & Collaboration

#### 3.8.1 Multi-User Support / Workspaces

| | |
|---|---|
| **Who has it** | Open WebUI (multi-user + RBAC), AnythingLLM (multi-user workspaces), GPT4All (enterprise/team) |
| **Owlynn status** | Strictly single-user. `user_id` is hardcoded to `"owner"` in Mem0. Projects are single-user workspaces. |
| **Effort** | Major (3–5 weeks) |
| **Impact** | **Low.** Owlynn is a personal desktop agent running on a single machine (M4 Air). Multi-user support is architecturally misaligned with: |
|  | - Local-first operation (one machine, one user) |
|  | - LM Studio (single model server, cannot serve concurrent users efficiently) |
|  | - Memory budget (24 GB on M4 Air leaves no room for concurrent user sessions) |
| **Technical approach** | **Do not implement.** If shared access is ever needed, recommend Open WebUI or AnythingLLM as complementary tools. Owlynn's value is deep single-user personalization. |

---

### 3.9 Sharing & Community

#### 3.9.1 Community Model/Character/Skill Sharing

| | |
|---|---|
| **Who has it** | Open WebUI (community sharing), AnythingLLM (agent skills marketplace) |
| **Owlynn status** | No sharing mechanism. Skills are local `.md` files. |
| **Effort** | Medium (2–3 days) |
| **Impact** | **Low-Medium.** Builds community but premature for a solo-dev project. |
| **Technical approach** | A GitHub-based registry is the simplest approach: |
|  | 1. Create `owlynn-hub` repo with structured directories: `skills/`, `personas/`, `plugins/` |
|  | 2. Owlynn fetches the registry index and lets users browse/install with one click |
|  | 3. Installed content goes to `~/.owlynn/community/` |
|  | 4. **Defer** until there's a user base. The persona system (§3.6.2) and plugin system (§3.4.1) should be built first. |

---

## 4. Prioritized Recommendations

### Tier 1: Do Now (Highest Impact / Lowest Effort)

| # | Feature | Status | Effort | Impact |
|---|---------|--------|--------|--------|
| 1 | **OpenAI-compatible local API server** | ✅ Basic (`:8000/v1/chat/completions`) | Polish 2–4h | Scripting, IDE integration |
| 2 | **CLI tool (`owlynn`)** | ✅ Basic (`src/cli.py`) | Polish 1–2h | Terminal access |
| 3 | **Chat format templates / model presets** | ❌ Not done | 2–3 hours | Smoother model switching |
| 4 | **Image upload UX** | ✅ Done (composer drag-and-drop) | — | Vision routing works |

### Tier 2: Do Next (Highest Impact / Medium Effort)

| # | Feature | Effort | Impact | Parities |
|---|---------|--------|--------|----------|
| 5 | **LocalDocs-style auto document indexing** | 3–5 days | **Very High** — biggest remaining UX gap | GPT4All, Open WebUI |
| 6 | **Extension/plugin system** (MCP + local plugins) | 4–7 days | **High** | Open WebUI, Jan |
| 7 | **Custom agent personas** | 3–5 days | **High** | AnythingLLM |
| 8 | **In-app model browser** | 3–5 days | **High** | LM Studio, Jan |
| 9 | **Content extraction polish** (Docling tool surface) | 1–2 days | **Medium** | Open WebUI |

### Tier 3: Consider Later (Lower Impact or Higher Effort)

| # | Feature | Effort | Impact | Parities |
|---|---------|--------|--------|----------|
| 10 | **Voice input (push-to-talk Whisper)** | 2–4 days | **Medium** — simpler than Live Talk, 80% of value | Open WebUI |
| 11 | **Python/TypeScript SDK** | 2–4 days | **Medium** — superseded by OpenAI-compatible API + `openai` package | LM Studio, GPT4All |
| 12 | **Thread organization** (search, pin, tag, date-group chats) | 2–3 days | **Medium** — quality of life as conversations grow | Jan |
| 13 | **Community skill/persona registry** | 2–3 days | **Low-Medium** — premature without user base | Open WebUI |

### Tier 4: Defer / Do Not Implement

| # | Feature | Reason |
|---|---------|--------|
| 14 | Multi-user support / RBAC | Conflicts with local-first single-machine architecture |
| 15 | Data connectors (Slack, GitHub, etc.) | Maintenance burden; MCP servers cover this use case |
| 16 | Tool pipelines / compute offloading | Premature optimization; async tool execution is sufficient |
| 17 | Model performance benchmarking | Nice-to-have, not essential |
| 18 | Embeddable chat widget | Irrelevant for a desktop agent |
| 19 | More web search providers | Current 5-tier pipeline is already robust |
| 20 | Enterprise/team features | Solo dev project, personal use |

---

## 5. Implementation Roadmap (Suggested Order)

### Sprint 1: Quick Wins — **mostly done** (2026-06-07)
```
✅ API Server → ✅ CLI → ✅ Image Upload UX → ⬜ Chat Templates
```
Remaining: chat format presets, API/CLI polish (auth, packaged `owlynn` shim).

### Sprint 2: RAG & Models (2–3 weeks)
```
Document Indexing (LocalDocs) → In-App Model Browser → Docling tool surface
```
Deliverables: "Drop a folder, ask questions" works. Single-app model management.

### Sprint 3: Extensibility (2–3 weeks)
```
Plugin System → Custom Personas → Thread Organization
```
Deliverables: Community-extensible tools. Specialized agents for different workflows.

### Sprint 4+: Polish & Growth
```
Voice Input → SDK → Community Registry
```
Deliverables: Nice-to-haves as user base grows.

---

## 6. Competitive Positioning After Recommended Changes

| Dimension | Owlynn Now (2026-06-07) | Owlynn After Tier 2 | Best Competitor |
|-----------|---------------------------|----------------------|-----------------|
| Model routing intelligence | **Best in class** — 3-way + HITL + cloud brief | Same | No direct equivalent |
| Security / HITL | **Best in class** | Same | No competitor has equivalent |
| Agent orchestration | **Best in class** — LangGraph | Same | Unique in this space |
| Programmatic API | Basic OpenAI-compatible (`:8000`) | Polished + documented | Jan |
| Document RAG | Knowledge Cache + Docling ingest; **no** auto folder index | Auto-indexing + search tool | GPT4All (LocalDocs) |
| Model management UX | `defaults.yaml` + LM Studio | In-app browser + presets | LM Studio |
| Tool ecosystem | 20+ built-in + MCP | Plugin system + MCP | Open WebUI |
| Custom agents | Single persona + skills | Persona system | AnythingLLM |
| Voice input | None | Push-to-talk Whisper | Open WebUI |
| CLI / automation | Basic `src/cli.py` | Packaged CLI + SDK docs | LM Studio |
| Multi-user | ❌ (by design) | ❌ (by design) | Open WebUI |
| Image attachments | ✅ Composer drag-and-drop | Same | AnythingLLM |

**Owlynn's moat:** LangGraph orchestration + security proxy + hybrid local/cloud routing (DeepSeek V4 with anonymization + prefix cache optimization). Recommended Tier 2 features fill parity gaps without diluting this differentiator.

---

## 7. Key Design Principles (Preserving Owlynn's Identity)

These constraints should guide all feature implementation:

1. **Local-first always** — No feature may require cloud connectivity for its core function. Cloud features (e.g., Mistral OCR) must be opt-in with clear UX indicators.
2. **Security proxy gating** — Any new tool or extension must route through `security_proxy`. HITL approval applies by default for destructive operations.
3. **Memory budget discipline** — New features must not exceed the M4 Air 24 GB envelope (refer to `docs/PERFORMANCE_SLOS.md` degradation ladder).
4. **Solo-dev maintainability** — Features should not create ongoing maintenance burdens. Prefer leveraging existing infrastructure (Qdrant, Redis, MCP) over new services.
5. **Build on strengths** — Leverage the LangGraph graph, router, and tool infrastructure rather than circumventing them.

## Related

- [`docs/architecture/overview.md`](architecture/overview.md) — current system architecture
- [`docs/CLOUD-LLM-ARCHITECTURE.md`](CLOUD-LLM-ARCHITECTURE.md) — cloud connection and caches
- [`docs/architecture/DEEPSEEK_V4_INTEGRATION.md`](architecture/DEEPSEEK_V4_INTEGRATION.md) — DeepSeek V4 optimization reference
- [`docs/architecture/KNOWLEDGE_CACHE.md`](architecture/KNOWLEDGE_CACHE.md) — conversation knowledge layer
- [`docs/README.md`](README.md) — project documentation map
- [`docs/INDEX.md`](INDEX.md) — documentation index

## Last updated

2026-06-07 — architecture, routing, models, API/CLI/image status, Docling/Knowledge Cache, Tier 1 completion
