---
last_verified: 2026-05-26
auto_generated: false
purpose: "Single entry point for AI agents and human developers. Combines navigation index, architecture quick-reference, and development rules."
---

# Owlynn Project Guide

Single merged guide replacing `AI_AGENT_INDEX.md`, `AI_AGENT_PROJECT_GUIDE.md`, and `HUMAN_PROJECT_GUIDE.md`. Provides navigation, architecture overview, and development rules in one document.

Related documents: `docs/ARCHITECTURE_OVERVIEW.md` (full architecture), `docs/STATUS.md` (active status and risks), `docs/ADR.md` (architecture decisions), `docs/BUG-ANALYSIS.md` (bug inventory).

---

## Section 1: Navigation Index

Fastest entry point for locating source files, contracts, and tests before making changes.

### Routing and Model Behavior

| File | Role |
|------|------|
| `src/agent/nodes/router.py` | Router node implementation |
| `src/agent/llm.py` | LLMPool singleton |
| `src/agent/swap_manager.py` | M-tier model hot-swap |
| `src/agent/nodes/complex.py` | Complex reasoning node |
| `tests/test_router_properties.py` | Router property tests |
| `tests/test_llm_pool.py` | LLM pool tests |
| `tests/test_swap_manager.py` | Swap manager tests |

### WebSocket/API Contract

| File | Role |
|------|------|
| `src/api/routes/` & `src/api/ws/` | Backend REST + WebSocket |
| `docs/CHAT_PROTOCOL.md` | WS event contract |
| `docs/API_REFERENCE.md` | REST endpoint reference |
| `frontend-v2/src/App.tsx` | Frontend WS consumer |
| `frontend-v2/src/lib/tauriBridge.ts` | Tauri IPC bridge |
| `tests/test_websocket_event_contract.py` | WS contract tests |
| `tests/test_websocket_model_key_updates.py` | Model key update tests |
| `tests/test_frontend_backend_alignment.py` | Frontend/backend alignment |

### Project/Workspace State and CRUD

| File | Role |
|------|------|
| `src/memory/project.py` | Project CRUD manager |
| `src/config/settings.py` | Workspace roots, project path rules |
| `frontend-v2/src/state/useAppStore.ts` | Zustand store |
| `frontend-v2/src/components/MemoryPanel.tsx` | Memory panel |
| `frontend-v2/src/components/AppShell.tsx` | App shell layout |
| `docs/BUG-ANALYSIS.md` | Bug inventory |
| `tests/test_crud_operations.py` | CRUD tests |
| `tests/test_crud_properties.py` | CRUD property tests |
| `tests/test_project_context_isolation_properties.py` | Project isolation tests |
| `frontend-v2/src/components/__tests__/components.extended.test.tsx` | Component tests |

### Cloud Fallback and Anonymization

| File | Role |
|------|------|
| `src/agent/anonymization.py` | PII scrubbing engine |
| `src/agent/nodes/complex.py` | Cloud path fallback |
| `tests/test_cloud_fallback_anonymization_leak.py` | Anonymization leak tests |
| `tests/test_anonymization_properties.py` | Anonymization property tests |
| `tests/test_complex_node_properties.py` | Complex node tests |

### Tooling and Security Gating

| File | Role |
|------|------|
| `src/agent/tool_sets.py` | ToolboxRegistry |
| `src/agent/nodes/security_proxy.py` | HITL gate |
| `src/tools/` | Tool implementations |
| `docs/TOOLS.md` | Tool reference |

### Bug Tracking

| ID | Severity | Description |
|----|----------|-------------|
| BUG-1 | CRITICAL | Persona/system prompt leaks into first assistant response |
| BUG-2 | HIGH | Orchestration panel empty after message processing |
| BUG-3 | HIGH | Memory panel shows "Loading..." indefinitely |
| BUG-4 | MEDIUM | Chat auto-title defaults to "New Chat" |
| BUG-5 | MEDIUM | Safe Mode dropdown depends on Tauri IPC, no browser fallback |
| BUG-6 | LOW | Tool Execution panel shows permanent mock data |
| BUG-7 | LOW | Workspace delete shows wrong operator note |
| BUG-8 | LOW | Audit & Verify sub-panel doesn't expand |

### Canonical Documentation Map

| Document | Purpose |
|----------|---------|
| `README.md` | Project overview and setup |
| `docs/PROJECT_GUIDE.md` | This file -- navigation, architecture, rules |
| `docs/API_REFERENCE.md` | API contract |
| `docs/CHAT_PROTOCOL.md` | WebSocket contract |
| `docs/STATUS.md` | Active status and risks |
| `docs/ADR.md` | Architecture decisions |
| `docs/PERFORMANCE_SLOS.md` | Performance & memory SLOs |
| `docs/BUG-ANALYSIS.md` | Bug analysis and audit reports |
| `docs/CLOUD-LLM-ARCHITECTURE.md` | Cloud LLM connection architecture, security, retry/fallback |
| `docs/ENGINEERING_IMPROVEMENTS.md` | Engineering improvement backlog |

---

## Section 2: Architecture Quick-Reference

Owlynn is a local-first AI coworker that runs a LangGraph agent backend with a Tauri frontend. Keeps most reasoning and data on your machine while supporting optional cloud escalation and external tools.

### Tech Stack

| Layer | Technology | Location |
|-------|-----------|----------|
| Frontend | Tauri + React/TypeScript | `frontend-v2/` |
| Backend | FastAPI + WebSocket streaming | `src/api/routes/` & `src/api/ws/` |
| Agent orchestration | LangGraph nodes | `src/agent/` |
| Memory | JSON + Mem0/Qdrant | `src/memory/` |
| Tools | File ops, web, notebook, docs, skills, MCP | `src/tools/` |

### Data Flow

1. User message enters WebSocket chat endpoint
2. Memory context is injected
3. Router chooses simple vs complex model path
4. Complex path may call tools through security proxy approval
5. Response is streamed back and memory is updated

### Graph Topology

```
START -> memory_inject -> router -> simple -> memory_write -> END
                               -> complex_llm <..........................+
                                    |                                |
                               security_proxy                       |
                                    |                                |
                               tool_action ---------------------------+
                                    |
                               memory_write -> END
```

### Entry Points

| Component | Path |
|-----------|------|
| Backend entry | `src/api/server.py` |
| Frontend entry | `frontend-v2/src/App.tsx` |
| Full architecture | `docs/ARCHITECTURE_OVERVIEW.md` |
| LangGraph node details | `docs/AGENT_FLOW.md` |
| Tool reference | `docs/TOOLS.md` |
| REST/WS endpoints | `docs/API_REFERENCE.md` |

---

## Section 3: Development Rules

Prioritize reliability, traceability, and safe tool usage over novelty. Keep changes explainable and compatible with local runtime constraints.

### Execution Rules

1. Keep diffs focused to the user request
2. Preserve security proxy behavior around tool execution
3. When touching routing/model behavior, update or add targeted tests
4. Avoid mixing unrelated frontend/backend/docs changes in one commit
5. Prefer deterministic fallbacks over silent failure paths

### Model-Routing Expectations

| Concern | Requirement |
|---------|-------------|
| Router | Decides among: simple, complex-default, vision, long-context, cloud |
| Complex node | Must preserve safe tool binding, fallback chain visibility, blank-response fallback, anonymization/deanonymization correctness for cloud paths |

### Minimum Coverage by Area

| Change Area | Required Tests |
|-------------|---------------|
| Model/routing | `tests/test_llm_pool.py`, `tests/test_swap_manager.py`, `tests/test_router_web_intent.py` |
| Anonymization | `tests/test_anonymization*.py` |
| Fallback behavior | `tests/test_complex_node_properties.py` |

### Before Commit Checklist

1. Scope changes to one risk/theme
2. Update tests in the touched area
3. Verify behavior with targeted test runs
4. Update docs when API/WS behavior changes
5. Confirm `docs/STATUS.md` still reflects current risk state

### Local Development Quick-Start

```bash
pip install -r requirements.txt
# Start supporting services (Redis/Qdrant via docker-compose)
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
pytest tests/ -v
cd frontend-v2 && npx vitest run
```

### Definition of Done

1. Code compiles and tests pass for changed area
2. User-facing behavior is verified (or explicitly noted if not runnable)
3. Documentation updated when behavior/workflow changes

### Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Local-first architecture | Data privacy, offline operation | Cloud fallback requires API keys |
| Security proxy HITL | Safe tool execution | Approval latency for sensitive operations |
| LangGraph orchestration | Stateful, testable graph | More complex than linear pipelines |
| Deterministic fallbacks preferred | Predictable behavior | May not always choose optimal model |
| Single Zustand store | Simple state management | No store segmentation |
