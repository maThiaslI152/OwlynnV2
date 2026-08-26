# AGENTS.md — Agent Onboarding

> **Purpose:** Single entry point for every Cursor/IDE agent session. Read this before touching code.

## Quick start (run app)

→ [`docs/guides/dev-startup.md`](docs/guides/dev-startup.md) — prerequisites, `./setup.sh` (first time), `./start.sh` (daily launch)

## Repo layout (top-level)

| Path | Role |
|------|------|
| `src/agent/` | LangGraph graph, nodes, router, LLM pool, HITL |
| `src/api/` | FastAPI routes + WebSocket handler |
| `src/config/` | `defaults.yaml` — single source of truth |
| `src/memory/` | STM/LTM/personal memory managers, thought graph |
| `src/tools/` | Agent tool implementations & dynamic ToolRegistry |
| `src/pdf/` | Unified PDF text intake (StirlingPDF + PyMuPDF fallback) |
| `src/integrations/` | External service clients (StirlingPDF, Shodan, Censys, Burp) |
| `frontend-v2/` | React 19 + Electron UI |
| `tests/` | Python unit, property, contract, and benchmark tests |
| `scripts/ci.sh` | Local CI (run before push: `./scripts/ci.sh --quick`) |
| `scripts/run_local_frontier_eval.py` | Frontier eval — `--profile auto/local/cloud` |
| `scripts/run_browser_eval.py` | Playwright conversation eval (12 prompts) |
| `docs/` | Structured documentation (see [`docs/README.md`](docs/README.md) and [`docs/INDEX.md`](docs/INDEX.md)) |

## Task routing

| I want to… | Read | Edit |
|------------|------|------|
| Change routing / model selection | [`docs/development/EXTENDING_AGENT.md`](docs/development/EXTENDING_AGENT.md) | `src/agent/routing/`, `src/agent/core/tool_first_web.py`, `src/config/defaults.yaml` |
| Change LLM provider (LM Studio / Ollama / Cloud) | [`docs/guides/lm_studio.md`](docs/guides/lm_studio.md) | `src/config/defaults.yaml`, `src/agent/llm.py` |
| Change PDF intake / OCR | [`docs/guides/dev-startup.md`](docs/guides/dev-startup.md) | `src/pdf/intake.py`, `src/integrations/stirling_pdf.py`, `docker-compose.yml` |
| Add or change a tool | [`docs/features/TOOLS.md`](docs/features/TOOLS.md) | `src/tools/`, `src/tools/registry.py`, `src/agent/tool_sets.py` |
| Change WebSocket events / protocol | [`docs/development/CHAT_PROTOCOL.md`](docs/development/CHAT_PROTOCOL.md) | `src/api/ws/handler.py`, `frontend-v2/src/` |
| Fix memory / context injection | [`docs/features/MEMORY.md`](docs/features/MEMORY.md) | `src/agent/nodes/memory.py`, `src/memory/` |
| Tune semantic cache (threshold, TTL) | [`docs/features/SEMANTIC_CACHE.md`](docs/features/SEMANTIC_CACHE.md) | `src/memory/semantic_cache.py`, `src/api/ws/handler.py` |
| Change context summarization / compaction | — | `src/agent/nodes/summarize.py` |
| Change Postgres memory / extraction / saver | [`docs/architecture/POSTGRES_MEMORY_LIFECYCLE.md`](docs/architecture/POSTGRES_MEMORY_LIFECYCLE.md) | `src/memory/extraction/worker.py`, `src/agent/core/checkpointer.py` |
| Change HITL / approvals | [`docs/architecture/HITL.md`](docs/architecture/HITL.md) | `src/agent/hitl/`, `src/agent/nodes/{scope_clarify,plan_review,security_proxy}.py`, `src/agent/core/ask_user_guards.py` |
| Debug a symptom | [`docs/debugging/README.md`](docs/debugging/README.md) | Follow symptom → file table |
| Change cloud reasoning / anonymization | [`docs/architecture/CLOUD-LLM-ARCHITECTURE.md`](docs/architecture/CLOUD-LLM-ARCHITECTURE.md) | `src/agent/core/complex*.py`, `src/agent/cloud/` |
| Change Eco-Mode / battery throttling | — | `src/api/power_monitor.py`, `src/agent/routing/router.py`, `src/api/ws/handler.py` |
| Change idle resource management | — | `src/api/idle_manager.py`, `src/api/server.py`, `src/pdf/intake.py` |
| Run or configure the app | [`docs/guides/dev-startup.md`](docs/guides/dev-startup.md) | `start.sh`, `setup.sh`, `.env` |
| Run CI / tests / evaluation | [`docs/standards/EVALUATION.md`](docs/standards/EVALUATION.md) | `scripts/ci.sh`, `scripts/run_*_eval.py` |
| Change mode system (Normal/Study/Pentest) | [`docs/features/MODES.md`](docs/features/MODES.md) | `frontend-v2/src/components/ModeSwitcher.tsx`, `src/api/ws/handler.py` |
| Change study tools / courses | [`docs/features/STUDY.md`](docs/features/STUDY.md) | `src/tools/study_tools.py`, `src/api/routes/study.py`, `skills/` |
| Change pentest tools & attack chain | [`docs/features/PENTEST.md`](docs/features/PENTEST.md) | `src/tools/pentest_tools.py`, `src/agent/pentest/`, `src/agent/tool_sets.py` |
| Change pentest live terminal / Kali Lima | [`docs/features/PENTEST.md`](docs/features/PENTEST.md) | `src/tools/screen_assist/kali_stream.py`, `frontend-v2/src/components/LiveTerminal.tsx`, `lima/kali.yaml` |
| Change pentest multi-agent executor / task graph | [`docs/features/PENTEST.md`](docs/features/PENTEST.md) | `src/agent/pentest/executor.py`, `src/agent/pentest/domain_prompts.py`, `src/agent/pentest/task_graph.py` |
| Change pentest integrations & MCP | [`docs/features/PENTEST.md`](docs/features/PENTEST.md) | `src/integrations/`, `src/config/defaults.yaml`, `mcp_config.json` |
| Change browser extension | [`docs/features/BROWSER_EXTENSION.md`](docs/features/BROWSER_EXTENSION.md) | `browser-extension/`, `src/api/routes/browser_extension.py` |
| Package Electron app | [`docs/guides/app-release.md`](docs/guides/app-release.md) | `scripts/build_backend_bundle.sh`, `frontend-v2/electron/` |
| Change Thought Graph / Mindmap Canvas | [`docs/features/MODES.md`](docs/features/MODES.md) | `src/memory/thought_graph.py`, `src/api/routes/thought_graph.py`, `frontend-v2/src/components/mindmap/` |

## Mode System & Model Architecture

| Mode | Response Style | Scenario | Canvas Renderer | Header / Status |
|------|---------------|----------|-----------------|-----------------|
| **Normal** | User choice | Auto-detected | **Coggle Organic Mindmap** (curved pastel bezier branches) | Mode pills in `MacMenuBar`, System/Brave in `StatusBar` |
| **Study** | `learning` (forced) | `study` (forced) | **Mastery Knowledge Tree** (Coggle-style progress branches) | Mode pills in `MacMenuBar`, Study countdown & stats |
| **Pentest** | `concise` (forced) | `pentest` (forced) | **Autodesk Maya Hypershade / Blueprint Editor** (CAD grid & pins) | Mode pills in `MacMenuBar`, Scope & attack graph |

- **Unified Local Model:** `gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m` powers routing, simple chat, memory extraction, and pentest mode (zero-latency switching).
- **Toolsets:**
  - **Pentest (67 tools):** Engagement, findings, targets, credentials, evidence, wireless, attack chain, screen assist, network, web, vuln, exploitation, post-exploitation, OSINT, AD, password, cloud, and reporting. See [`docs/features/PENTEST.md`](docs/features/PENTEST.md).
  - **Study (16 tools):** Course management, flashcards, SM-2 review, quiz sessions, mastery records, and study sheet exports. See [`docs/features/STUDY.md`](docs/features/STUDY.md).
  - **Core Tools:** File I/O, web search, notebook, and data connectors. See [`docs/features/TOOLS.md`](docs/features/TOOLS.md).

## Critical Rules & Guidelines

### Prompt Caching & LLM Stability
- **Prompt Caching is Sacred**: Keep system prompts byte-stable by separating static templates from volatile runtime state.
- **Deterministic Tool Ordering**: Always sort tool definitions alphabetically before binding to LLM clients.
- **Zero Synthetic Human Injections**: Never inject synthetic `HumanMessage` prompts mid-turn; embed guidance in `ToolMessage`.
- **Whitespace Preservation**: Never call `.strip()` on intermediate streaming chunks.

### Local-First Latency
- **Default `cloud_routing_mode=local_only`**: Fast local execution without redundant model swaps.
- **Tool-First Bypasses**: High-confidence queries (web search, list/read) execute deterministic tool injection before LLM planning. Clear stale `_tool_first_web_phase=done` on new turns.
- **Simple max tokens default 128**: Keeps greetings and trivia turns snappy.

### Security & HITL
- **Execution policy default is `require_approval`**: All mutating/sensitive tools trigger HITL review by default.
- **Auth & Boundaries**: `/v1/chat/completions` requires token verification; web fetches wrapped in `<web_context>`; SSRF protection on downloads; scope guard blocks destructive commands (`rm -rf /`, `mkfs`, etc.).

### Architecture & Resilience
- **Host macOS Only**: FastAPI backend runs natively on host macOS for screen assist/tmux direct access (never containerize the Python backend). Supporting services (Postgres, StirlingPDF) run in Docker/Podman.
- **Fault-Isolated Execution**: Tool executions and WebSocket event loops are wrapped in try/except; rotating crash logs saved to `~/.owlynn/logs/crash.log`.
- **UI & Error Handling**: Surface network/API failures visibly via toasts (e.g. `react-hot-toast`); clean `dist/` before Electron build.
- **Evaluation Truth**: Use WebSocket `idle` status event as definitive turn completion, never DOM polling.

## Recent Milestones

- **2026-08-26:** E2E Topic Drift latency optimizations: fast in-memory exact cache (<1ms), clean pronoun expansion for tool-first web, multi-turn history trimming (150 chars), simple route temperature & token budget tuning.
- **2026-08-26:** Usable multi-turn chat: tool-first sticky phase cleanup, list/read short-circuit, Postgres memory lifecycle docs, Podman 4GB.
- **2026-08-24:** v0.3.1 Desktop release: local tool bind cap, Mindmap UX enhancements, packaged `Owlynn-0.3.1-arm64.dmg`.
- **2026-08-23:** Offline Chart.js visualization, Unified Gemma 4 12B local architecture, Coggle/Hypershade canvas engine.
- *Detailed changelogs are available in [`docs/changes/`](docs/changes/).*
