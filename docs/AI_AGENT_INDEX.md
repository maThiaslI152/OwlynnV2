---
last_verified: 2026-05-26
auto_generated: false
---

# AI Agent Navigation Index

## Overview

Fastest entry point for AI agents working in Owlynn. Locate source files, contracts, and tests before making changes.

Current status: **Phase 7 complete**. All phases through 7 are done.

## Entry Points

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
| `src/api/server.py` | Backend WebSocket + REST |
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

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Single-source navigation index | One place to find all relevant files | Must be kept up to date |
| Categorization by concern area | Maps directly to developer tasks | Some files appear in multiple categories |

## Testing

### Before Commit Checklist

1. Scope changes to one risk/theme
2. Update tests in the touched area
3. Verify behavior with targeted test runs
4. Update docs when API/WS behavior changes
5. Confirm `docs/STATUS.md` still reflects current risk state

## Configuration

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
| `docs/HUMAN_PROJECT_GUIDE.md` | Human workflow guide |
| `docs/AI_AGENT_PROJECT_GUIDE.md` | AI execution guide |
| `docs/API_REFERENCE.md` | API contract |
| `docs/CHAT_PROTOCOL.md` | WebSocket contract |
| `docs/STATUS.md` | Active status and risks |
| `docs/ADR.md` | Architecture decisions |
| `docs/PERFORMANCE_SLOS.md` | Performance & memory SLOs |
| `docs/BUG-ANALYSIS.md` | Bug analysis and audit reports |
| `docs/ENGINEERING_IMPROVEMENTS.md` | Engineering improvement backlog |
