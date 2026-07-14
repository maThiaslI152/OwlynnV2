# AGENTS.md — Agent Onboarding

> **Purpose:** Single entry point for every Cursor agent session. Read this before touching code.

## Quick start (run app)

→ [`docs/guides/dev-startup.md`](docs/guides/dev-startup.md) — prerequisites, `./setup.sh` (first time), `./start.sh` (daily launch)

## Before editing code (required reads)

1. [`docs/development/PROJECT_GUIDE.md`](docs/development/PROJECT_GUIDE.md) — file map by task
2. [`docs/architecture/overview.md`](docs/architecture/overview.md) — system shape, modules, data flow
3. [`docs/standards/coding-style.md`](docs/standards/coding-style.md) — naming, patterns, lint

## Repo layout (top-level)

| Path | Role |
|------|------|
| `src/agent/` | LangGraph graph, nodes, router, LLM pool, HITL |
| `src/api/` | FastAPI routes + WebSocket handler |
| `src/config/` | `defaults.yaml` — single source of truth |
| `src/memory/` | STM/LTM/personal memory managers |
| `src/tools/` | Agent tool implementations |
| `src/pdf/` | Unified PDF text intake (StirlingPDF + PyMuPDF fallback) |
| `src/integrations/` | External service clients (StirlingPDF) |
| `frontend-v2/` | React + Electron UI |
| `tests/` | Python unit, property, contract, and benchmark tests |
| `scripts/ci.sh` | Local CI (run before push) |
| `scripts/run_browser_eval.py` | Playwright conversation eval (12 prompts) |
| `scripts/run_local_frontier_eval.py` | Frontier eval — `--profile auto/local/cloud`, `--cloud-off`, `--strict-cloud` |
| `scripts/run_educator_eval.py` | Educator eval (EDU1–EDU8) — `--strict-cloud` |
| `scripts/archive/` | Retired one-off patch scripts (not CI) |
| `scripts/manual/` | Live tool smoke scripts (not pytest) |
| `docs/evaluations/` | Evaluation run reports (write after significant evals) |

## Task routing

| I want to… | Read | Edit |
|------------|------|------|
| Change routing / model selection | [`docs/development/EXTENDING_AGENT.md`](docs/development/EXTENDING_AGENT.md) | `src/agent/nodes/router.py`, `src/agent/router/`, `src/config/defaults.yaml` |
| Change LLM provider (LM Studio / Ollama) | — | `src/config/defaults.yaml`, `src/agent/llm.py` |
| Change PDF intake / OCR | [`docs/guides/dev-startup.md`](docs/guides/dev-startup.md) | `src/pdf/intake.py`, `src/integrations/stirling_pdf.py`, `docker-compose.yml` |
| Add or change a tool | [`docs/features/TOOLS.md`](docs/features/TOOLS.md) | `src/tools/`, `src/agent/tool_sets.py` |
| Change WebSocket events | [`docs/development/CHAT_PROTOCOL.md`](docs/development/CHAT_PROTOCOL.md) | `src/api/ws/handler.py`, `frontend-v2/src/` |
| Fix memory / context injection | [`docs/features/MEMORY.md`](docs/features/MEMORY.md) | `src/agent/nodes/memory.py`, `src/memory/` |
| Tune semantic cache (threshold, TTL) | [`docs/features/SEMANTIC_CACHE.md`](docs/features/SEMANTIC_CACHE.md) | `src/memory/semantic_cache.py`, `src/api/ws/handler.py` |
| Change LangGraph checkpoints (PostgreSQL) | — | `src/agent/core/checkpointer.py` |
| Change Redis memory / extraction queue | [`docs/architecture/REDIS_LIFECYCLE.md`](docs/architecture/REDIS_LIFECYCLE.md) | `src/memory/extraction/worker.py` |
| Change HITL / approvals | [`docs/HITL.md`](docs/HITL.md) | `src/agent/hitl/`, `src/agent/nodes/{scope_clarify,plan_review,security_proxy}.py` |
| Debug a symptom | [`docs/debugging/README.md`](docs/debugging/README.md) | Follow symptom → file table |
| Change cloud / anonymization | [`docs/architecture/CLOUD-LLM-ARCHITECTURE.md`](docs/architecture/CLOUD-LLM-ARCHITECTURE.md) | `src/agent/nodes/complex.py`, `src/agent/nodes/complex_utils/` |
| Change Eco-Mode / battery throttling | — | `src/api/power_monitor.py`, `src/agent/routing/router.py`, `src/api/ws/handler.py` |
| Change idle resource management (LLM unload, StirlingPDF) | — | `src/api/idle_manager.py`, `src/api/server.py`, `src/api/ws/handler.py`, `src/pdf/intake.py` |
| Run or configure the app | [`docs/guides/dev-startup.md`](docs/guides/dev-startup.md) | `start.sh`, `setup.sh`, `.env` |
| Run CI / tests / evaluation | [`docs/standards/EVALUATION.md`](docs/standards/EVALUATION.md) | `scripts/ci.sh`, `scripts/run_*_eval.py` |
| Change mode system (Normal/Study/Pentest) | — | `frontend-v2/src/components/ModeSwitcher.tsx`, `frontend-v2/src/state/slices/modesSlice.ts`, `src/api/ws/handler.py` |
| Change study tools / courses | — | `src/tools/study_tools.py`, `src/api/routes/study.py`, `skills/` |
| Change pentest scenario | — | `scenarios/pentest/`, `src/memory/scenarios.py`, `frontend-v2/src/components/PentestScopePanel.tsx` |
| Change pentest tools | — | `src/tools/pentest_tools.py`, `src/agent/pentest/`, `src/agent/tool_sets.py` |
| Change pentest live terminal | — | `src/tools/screen_assist/kali_stream.py`, `frontend-v2/src/components/LiveTerminal.tsx` |
| Change pentest cloud proxy | — | `src/agent/routing/pentest_classifier.py`, `src/agent/routing/router.py`, `src/config/defaults.yaml` |
| Change pentest wireless tools | — | `src/tools/pentest_tools.py` (wifi_*), `lima/kali.yaml`, `src/agent/hitl/policy.py` |
| Change pentest attack chain | — | `src/agent/pentest/attack_chain.py`, `src/tools/pentest_tools.py` (auto_recon, suggest_next_steps) |
| Change pentest multi-agent executor | — | `src/agent/pentest/executor.py`, `src/agent/pentest/domain_prompts.py`, `src/agent/core/graph.py` |
| Change pentest task graph | — | `src/agent/pentest/task_graph.py`, `src/memory/pentest_engagement.py` |
| Change pentest integrations | — | `src/integrations/`, `src/config/defaults.yaml` (integrations.*), `mcp_config.json` |
| Change Burp Suite integration | — | `src/integrations/burp_mcp_server.py`, `mcp_config.json` |
| Change pentest reporting | — | `src/tools/pentest_reporting.py`, `src/tools/pentest_report.py` |
| Change pentest tools | — | `src/tools/pentest_tools.py`, `src/agent/pentest/`, `src/agent/tool_sets.py` |
| Change pentest live terminal | — | `src/tools/screen_assist/kali_stream.py`, `frontend-v2/src/components/LiveTerminal.tsx` |
| Change pentest cloud proxy | — | `src/agent/routing/pentest_classifier.py`, `src/agent/routing/router.py`, `src/config/defaults.yaml` |
| Change pentest wireless tools | — | `src/tools/pentest_tools.py` (wifi_*), `lima/kali.yaml`, `src/agent/hitl/policy.py` |
| Change pentest attack chain | — | `src/agent/pentest/attack_chain.py`, `src/tools/pentest_tools.py` (auto_recon, suggest_next_steps) |
| Change browser extension | [`docs/features/BROWSER_EXTENSION.md`](docs/features/BROWSER_EXTENSION.md) | `browser-extension/`, `src/api/routes/browser_extension.py` |
| Package Electron app | [`docs/guides/app-release.md`](docs/guides/app-release.md) | `frontend-v2/electron/`, `frontend-v2/electron-builder.yml` |
| Change background jobs / scheduler | — | `src/api/scheduler_manager.py`, `src/api/routes/scheduled_jobs.py` |
| Change config / settings UI | — | `src/api/routes/config.py`, `frontend-v2/src/components/SettingsPanel.tsx` |
| Change citations UI | — | `frontend-v2/src/components/CitationsList.tsx` |
| Change chat export API | — | `src/api/routes/export.py` |
| Change tool reranking | — | `src/agent/tool_reranker.py`, `src/agent/core/complex.py` |
| Change data connectors | — | `src/tools/data_connectors.py` |

## Mode System

Owlynn has three modes that change the UI, tools, and system prompt:

| Mode | Response Style | Scenario | Sidebar | Right Panel |
|------|---------------|----------|---------|-------------|
| **Normal** | User choice | Auto-detected | Standard projects/chats | Orchestration, cloud usage |
| **Study** | `learning` (forced) | `study` (forced) | Courses, exam countdown, study progress | Study progress, weak areas |
| **Pentest** | `concise` (forced) | `pentest` (forced) | Scope & constraints panel | (MVP: sidebar only) |

- Mode is persisted per-project in PostgreSQL (`ProjectModel.mode` field)
- Mode switcher is in the left sidebar top
- Mode → WS payload: frontend sends `scenario_id` to backend
- Backend maps `scenario_id` to forced response_style and scenario injection
- `src/memory/project.py`: `_PROJECT_WRITABLE_FIELDS` includes `mode`

## Pentest Mode — Local-Only with Cloud Proxy

Cloud APIs (DeepSeek, OpenAI, etc.) refuse security/pentest content. Pentest mode uses the local model by default. **Non-sensitive queries** (CVE lookups, methodology) can be routed to cloud via the proxy.

- Config: `models.pentest` in `defaults.yaml` — set `model_name` to a dedicated pentest model
- Falls back to `models.small` (Qwen3 VL 4B) if no pentest model configured
- Accessor: `ConfigLoader.get_pentest_model_name()`
- Pentest mode forces `scenario_id="pentest"` and `response_style="concise"`
- Router returns `complex-default` (not `complex-cloud`) for pentest
- **Cloud proxy**: `models.pentest.cloud_proxy.enabled` routes public knowledge queries to cloud
- **Pentest model**: Gemma 4 12B Coder Q4 (`gemma-4-12b-coder-fable5-composer2.5-v1@q4_k_m`)
  - Winner of pentest benchmark (84.1% overall, 41 tok/s)
  - Benchmark: `scripts/bench_pentest_models.py`
  - Results: `docs/evaluations/pentest-model-benchmark-2026-06-28.md`

### Pentest Tools (67 total)

| Category | Tools | Count |
|----------|-------|-------|
| Engagement | engagement_create, engagement_set_phase, engagement_data_set/get, engagement_notes, engagement_report, engagement_compare | 7 |
| Findings | finding_add, finding_list, finding_update | 3 |
| Targets | target_add, target_list | 2 |
| Credentials | credential_store, credential_list | 2 |
| Evidence | evidence_store, evidence_list, read_evidence | 3 |
| Wireless | wifi_scan, wifi_deauth, wifi_handshake_capture, wifi_crack_handshake, wifi_analyze_pcap, wifi_wps_scan | 6 |
| Attack Chain | suggest_next_steps, auto_recon, analyze_attack_surface | 3 |
| Screen Assist | capture_kali_terminal, run_kali_command, send_kali_input, kali_tmux_new_window, kali_tmux_list_windows | 5 |
| File/Report | read/write/edit/list/delete workspace, create_pdf, create_docx, notebook | 8 |
| Network | nmap_scan, masscan_scan, service_enum | 3 |
| Web App | nikto_scan, gobuster_scan, sqlmap_scan, header_check | 4 |
| Vuln Scanning | nuclei_scan, searchsploit, cve_lookup | 3 |
| Exploitation | metasploit_run, poc_validate | 2 |
| Post-Exploitation | privesc_check, credential_harvest | 2 |
| OSINT | subfinder, shodan_search, censys_search | 3 |
| Active Directory | bloodhound_run, kerberoast, ldap_enum | 3 |
| Password | hydra_attack, john_crack | 2 |
| Cloud | s3_enum | 1 |
| Reporting | poc_generator, cvss_calculator, compliance_mapper | 3 |
| Burp Suite MCP | burp_scan_target, burp_get_issues, burp_get_scan_status | 3 |

### Pentest Multi-Agent Architecture

Owlynn uses a **coordinator + executor** pattern for pentest automation:

- **Coordinator** (`complex_llm_node`): Analyzes engagement state, decides which subtask to run, processes results
- **Executor** (`pentest_executor` node): Runs focused subtasks with domain-specific prompts and tool subsets
- **Task Graph** (`PentestTaskGraph`): DAG tracking attack dependencies and task status per engagement

Domain prompts in `src/agent/pentest/domain_prompts.py` provide specialized methodology for each category (PTES, OWASP, MITRE ATT&CK).

### Pentest Integrations

| Service | Client | Tools |
|---------|--------|-------|
| Shodan | `src/integrations/shodan_client.py` | shodan_search (read-only) |
| Censys | `src/integrations/censys_client.py` | censys_search (read-only) |
| HackerOne | `src/integrations/hackerone_client.py` | hackerone_submit (HITL) |
| Burp Suite | `src/integrations/burp_mcp_server.py` | MCP server (stdio transport) |

### Pentest Infrastructure (Kali VM)

Owlynn uses **Lima** (Apple Virtualization Framework) to run Kali Linux locally on macOS.

| Component | Setup | RAM |
|-----------|-------|-----|
| Lima VM | `./scripts/setup-kali-lima.sh` | ~2GB |
| Kali tools | nmap, sqlmap, hydra, john, nikto, gobuster, aircrack-ng, masscan, nuclei, bloodhound, etc. | — |
| SSH | Key auth, port 60022, user `kali` | — |
| tmux | Session `main` for Owlynn screen assist | — |
| Live Terminal | WS streaming at `/ws/pentest/terminal` | — |

- Lima config: `lima/kali.yaml`
- VM name: `owlynn-kali`
- Auto-detected by pentest status API (`/api/pentest/status`)
- Bridged networking for raw socket access (nmap SYN scan, masscan)
- Falls back to remote Kali via SSH if Lima not available
- **Live terminal**: Real-time tmux output via WebSocket (`kali_stream.py`)
- **Multi-engagement**: Engagement tabs with switching, per-engagement isolation

## Study System

16 study tools in `src/tools/study_tools.py`:

| Tool | Purpose |
|------|---------|
| `course_register` | Register course, auto-creates workspace project when linked_files provided |
| `course_workspace_create` | On-demand workspace creation for existing course |
| `course_chat_create` | Create named chat in course project |
| `course_list` / `course_get` | List/get course metadata |
| `study_note_save` / `study_note_search` | Save/search study notes |
| `flashcard_deck_create` / `flashcard_review` | Create decks, SM-2 spaced repetition review |
| `flashcard_suggest` | Generate flashcard content from course files |
| `quiz_session_start` / `quiz_session_answer` | Multi-question quiz sessions |
| `study_session_log` | Log sessions for streak tracking |
| `study_weak_areas` | Detect weak topics from misconception history |
| `mastery_record` | Save mastery/misconception atoms to Mem0 |
| `export_study_sheet` | Export study guide as PDF/DOCX |

API endpoints: `GET /api/study/dashboard`, `GET /api/study/exam-countdown`

## Skip unless asked

- `docs/archive/` — superseded plans and legacy notes
- `docs/evaluations/` — conversation eval reports
- `docs/changes/` — per-feature changelogs from past work

## Before push

```bash
./scripts/ci.sh --quick
```

Pre-push hook runs this automatically. Skip only when intentional: `git push -o no-ci`.

## Learned Rules

### Evaluation Harness Modifications
When modifying or extending `scripts/run_local_frontier_eval.py` or any UI-driven test harness, **never rely on DOM element polling (e.g., `is_graph_busy`) to determine if a conversational turn is complete.** Always use the WebSocket event stream (specifically the `idle` status event) as the definitive source of truth to avoid race conditions during parallel tool execution or streaming delays.

### Frontend Error Handling
Do not allow API fetches or WebSocket unhandled promise rejections to fail silently with console warnings. Always surface operational and network failures visibly to the user using the project's toast notification library (e.g., `react-hot-toast`).

### Frontend UI Layouts & Imports
- **Flexible SVG Containers:** When building UI components with `lucide-react` or other SVG icons, use flexible properties (like `flex: 1` and `justifyContent`) rather than rigid paddings to prevent text clipping and overflow in constrained containers.
- **Strict Imports:** The TypeScript build strictly enforces `noUnusedLocals`. Always clean up unused imports immediately after refactoring components.

### Architecture & Containerization
Owlynn's Python FastAPI backend is strictly designed to run natively on the host OS (macOS) and should **never** be containerized. It requires direct host access for Screen Assist tools (tmux capture, Accessibility APIs). Only supporting services (Qdrant, Redis, StirlingPDF) are containerized via `start.sh`.

### Cache Key Generation for Chat Contexts
When generating cache keys for chat histories or context gatekeepers (e.g., in `cloud_payload.py`), ensure the key is resilient to follow-up messages. Always include the total message count (`len(messages)`) and a slice of the final message's content to guarantee cache invalidation on new turns.

### Security Hardening (2026-07-07)
- **Execution policy default is `require_approval`** — all sensitive tools (write, edit, delete, notebook) trigger HITL interrupt by default. Users can opt into `auto_approve` via profile setting.
- **`/v1/chat/completions` requires auth** — the OpenAI-compatible endpoint is outside `/api/*` middleware, so it has its own `_verify_openai_token()` check. `auto_approve_sensitive` is hardcoded to `False` (client cannot override).
- **Notebook sandbox is hardened** — `requests` and `httpx` removed from import whitelist. Only safe stdlib + data science modules allowed.
- **SSRF protection on downloads** — `download_to_workspace` uses `url_policy.py` to block private IPs, localhost, cloud metadata.
- **Prompt injection boundaries** — `fetch_webpage` output wrapped in `<web_context>` tags. Memory writes sanitized for injection patterns via `pii_scrubber.scrub_for_memory_write()`.
- **Destructive command blocking** — `scope_guard.py` blocks `rm -rf /`, `mkfs`, `dd` to device, fork bombs, etc. regardless of engagement state.

### Crash Logging & Tool Resilience (2026-07-09)
- **Tool execution is crash-proof** — `ToolNode.ainvoke()` in `complex.py` is wrapped in try/except. On failure, returns error ToolMessage so the LLM can inform the user gracefully.
- **Event forwarding is fault-isolated** — Per-event try/except in `forward_events` inner loop (`handler.py`). Bad events are logged and skipped instead of killing the forwarder.
- **Crash log at `~/.owlynn/logs/crash.log`** — Rotating (5MB, 3 backups). Captures: `faulthandler` (segfaults), `sys.excepthook` (main thread), `threading.excepthook` (background threads), `loop.set_exception_handler` (async tasks).
- **All tracebacks go to logs** — `traceback.print_exc()` replaced with `logger.error(..., exc_info=True)` throughout.
- **WebSocket auto-reconnect** — Frontend reconnects with exponential backoff (1s→16s, max 5 retries), re-sends last user message to retry failed graph run.

### Browser Extension (Manifest V3) Strictness
- **Explicit API Permissions:** Always explicitly add APIs (e.g., `"alarms"`) to the `permissions` array in `manifest.json`.
- **CSP Compliance:** Do not use `frame-src` within the `extension_pages` Content Security Policy, and avoid port wildcards (`:*`) in `connect-src`.

### LLM Text Streaming Parsing
- **Whitespace Preservation:** Never call `.strip()` (or similar whitespace-trimming functions) on intermediate text chunks during streaming (e.g., in `_strip_thinking_tags`), as it swallows spaces between words in the UI.

### Electron Build Workflow
- **Clean Build Directories:** Before running `npm run build` or `vite build` for the frontend, manually delete the `dist` directory (`rm -rf dist`) to prevent `ENOTEMPTY` errors.
- **Applying Changes:** Backend Python changes require an app restart. Frontend or manifest changes require a full `npm run build` to be packaged into the `.app` bundle.

## Related

- [`docs/README.md`](docs/README.md) — full documentation map
- [`docs/INDEX.md`](docs/INDEX.md) — machine-readable manifest (filter by `audience`)

P26-07-14 — Frontier Eval & WebSocket Stability Fixes: Patched App.tsx to clean up stale streaming states on dropped connections. Updated src/api/ws/handler.py to emit chunk/assistant.message for semantic cache hits, fixing invisible UI responses. Added ws_idle fallback timeout to scripts/run_local_frontier_eval.py. Restored benchmark to 91.32%. Changelog at docs/changes/frontier-eval-stability/CHANGELOG.md.
2026-07-12 — Pentest V4 Orchestration: Implemented phase-based pipeline orchestrator (`PipelineOrchestrator`), automated context truncation (`pentest_memory_node`), strict BFS/DFS methodology in `domain_prompts`, refactored `generate_pdf_report` for HTML-to-PDF rendering via StirlingPDF, and updated `poc_generator` to use LLM. Fixed frontend test imports. Changelog at docs/changes/pentest-v4-orchestration/CHANGELOG.md.
2026-07-12 — Frontend V2 Architecture & Tailwind Migration: Restructured React components into domain directories, integrated Tailwind CSS v4, replaced drag-and-drop with react-dropzone, built Data Connectors UI, added central ModalManager using Zustand and framer-motion, and implemented Voice Interaction (SpeechRecognition and TTS). Changelog at docs/changes/frontend-v2-architecture/CHANGELOG.md.
2026-07-10 — Phase 1 and 4 Roadmap Completion: Fixed HITL bypass, macOS Keychain for Fernet, Observer/Reflector 2-phase LLM pipeline, semantic tool reranking via Nomic, data connectors, APScheduler background jobs, Settings/Citations UI, Chat export. Changelog at docs/changes/phase-1-4-roadmap/CHANGELOG.md.
2026-07-09 — Performance Optimizations (Idle + Active): Parallel tool dispatch (asyncio.gather for independent tools); idle LLM unload after 15min via LM Studio REST API; StirlingPDF idle-shutdown (opt-in); follow-up continuation bypass skips LLM router classifier; file cache poll replaces asyncio.sleep(3). Changelog at docs/changes/performance-optimizations/CHANGELOG.md.
2026-07-09 — Eco-Mode Background Throttling and Intelligent Routing: Implemented battery monitoring via `pmset -g batt`. Background RAG extraction and file processing suspend when on battery. Router forces `complex-cloud` fallback. Frontend UI warning added for Pentest mode. Changelog at docs/changes/eco-mode/CHANGELOG.md.
2026-07-09 — Crash-proof tool execution: wrapped ToolNode.ainvoke() in try/except, per-event error isolation in WS forward_events, crash logging (faulthandler + sys.excepthook + threading.excepthook + asyncio handler) to ~/.owlynn/logs/crash.log, frontend error event handler, WebSocket auto-reconnect with exponential backoff and thread resumption. Changelog at docs/changes/crash-proof-logging-reconnect/CHANGELOG.md.
2026-07-08 — Pentest V3 features: multi-agent architecture (coordinator + executor pattern, PentestExecutor node, domain-specific prompts); 29 new tools across 9 categories (network, web, vuln, exploit, post-exploit, OSINT, AD, password, cloud); task graph (PentestTaskGraph DAG for attack dependency tracking); integrations (Shodan, Censys, HackerOne, Burp Suite MCP); enhanced reporting (PoC generator, CVSS calculator, compliance mapper). 67 total pentest tools. Changelog at docs/changes/pentest-v3-multi-agent/CHANGELOG.md.
2026-07-08 — Pentest V2 features: live terminal streaming (WS-based, replaces 3s polling); cloud pentest proxy (CVE/methodology queries to cloud, target data stays local); wireless pentest tools (6 wifi_* tools, aircrack-ng suite, HITL gating); multi-engagement support (tabs, switching, cross-engagement compare); attack chain automation (auto_recon, suggest_next_steps, analyze_attack_surface). 38 total pentest tools. Changelog at docs/changes/pentest-v2-features/CHANGELOG.md.
2026-07-07 — Browser extension bugfixes: fixed extension crashing by adding `alarms` to permissions; improved MV3 CSP strictness; fixed frontend streaming whitespace bug by removing `.strip()` in `formatter.py`; added UI animation tracking for tool execution state.
2026-07-07 — Electron app packaging: .app with splash screen, backend spawning, tray, close-to-background, version display (v0.1.0). Atomic writes for user_profile.json and secrets.env. Browser extension bundled in .app Resources. Release guide at docs/guides/app-release.md. Task routing table updated with "Package Electron app" row.
2026-07-07 — Security hardening: execution policy default changed to require_approval; /v1/chat/completions auth enforced; notebook sandbox hardened; SSRF protection on downloads; prompt injection boundaries on web fetches and memory writes; destructive command blocking in scope guard. Task routing table updated with semantic cache and Redis lifecycle rows.
2026-07-04 — Frontend UI overhaul (glassmorphic dropdowns, accessible memory management) and critical bug fixes for WebSocket chunk streaming overhead / infinite loop in markdown parser. Frontier eval passes at 96.32%.
2026-07-02 — Production-readiness audit: PostgreSQL replaces `projects.json` for mode persistence; mode routing table updated to `modesSlice.ts`; task routing table updated to reference sliced store.
2026-07-10 — Phase 6: Migrated LangGraph checkpointer from Redis to PostgreSQL (`AsyncPostgresSaver` in `checkpointer.py`). Removed `_evict_stale_checkpoints` as state persistence is now native to Postgres. Semantic Cache and Extraction queue remain on Redis.
