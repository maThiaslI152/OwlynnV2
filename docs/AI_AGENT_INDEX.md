# AI Agent Navigation Index

This index is the fastest entry point for AI agents working in Owlynn.
Use it to locate the right source files, contracts, and tests before making changes.

## Current Delivery Status

- **Roadmap phase:** Phase 7 (Post-MVP Polish, complete)
- **Current verdict:** All phases through 7 are complete.

## Start Here By Task

### Routing and model behavior
- `src/agent/nodes/router.py`
- `src/agent/llm.py`
- `src/agent/swap_manager.py`
- `src/agent/nodes/complex.py`
- Tests:
  - `tests/test_router_properties.py`
  - `tests/test_llm_pool.py`
  - `tests/test_swap_manager.py`

### WebSocket/API contract work
- `src/api/server.py`
- `docs/CHAT_PROTOCOL.md`
- `docs/API_REFERENCE.md`
- Frontend consumer:
  - `frontend-v2/src/App.tsx`
  - `frontend-v2/src/lib/tauriBridge.ts`
- Tests:
  - `tests/test_websocket_event_contract.py`
  - `tests/test_websocket_model_key_updates.py`
  - `tests/test_frontend_backend_alignment.py`

### Project/workspace state and CRUD
- `src/memory/project.py`
- `src/config/settings.py` (workspace roots and project path rules)
- `frontend-v2/src/state/useAppStore.ts`
- `frontend-v2/src/components/MemoryPanel.tsx`
- `frontend-v2/src/components/AppShell.tsx`
- Bug analysis: `docs/BUG-ANALYSIS.md` (workspace creation failures, chat display issues)
- Tests:
  - `tests/test_crud_operations.py`
  - `tests/test_crud_properties.py`
  - `tests/test_project_context_isolation_properties.py`
  - `frontend-v2/src/components/__tests__/components.extended.test.tsx`

### Cloud fallback and anonymization
- `src/agent/anonymization.py`
- `src/agent/nodes/complex.py`
- Tests:
  - `tests/test_cloud_fallback_anonymization_leak.py`
  - `tests/test_anonymization_properties.py`
  - `tests/test_complex_node_properties.py`

### Tooling and security gating
- `src/agent/tool_sets.py`
- `src/agent/nodes/security_proxy.py`
- `src/tools/`
- Docs:
  - `docs/TOOLS.md`

## Canonical Documentation Map

- Project overview and setup: `README.md`
- Human workflow guide: `docs/HUMAN_PROJECT_GUIDE.md`
- AI execution guide: `docs/AI_AGENT_PROJECT_GUIDE.md`
- API contract: `docs/API_REFERENCE.md`
- WebSocket contract: `docs/CHAT_PROTOCOL.md`
- Active status and risks: `docs/STATUS.md`
- Architecture decisions: `docs/ADR.md`
- Live Talk deferred status (removed): `docs/LIVE_TALK_DEFERRED.md`
- Performance & memory SLOs: `docs/PERFORMANCE_SLOS.md`
- Engineering improvement backlog: `docs/ENGINEERING_IMPROVEMENTS.md`

## Before You Commit (Agent Checklist)

1. Scope changes to one risk/theme.
2. Update tests in the touched area.
3. Verify behavior with targeted test runs.
4. Update docs when API/WS behavior changes.
5. Confirm `docs/STATUS.md` still reflects current risk state.
