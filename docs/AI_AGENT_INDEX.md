# AI Agent Navigation Index

This index is the fastest entry point for AI agents working in Owlynn.
Use it to locate the right source files, contracts, and tests before making changes.

## Current Delivery Status

- **Roadmap phase:** Phase 6 (MVP Hardening)
- **Current verdict:** In progress
- **Reason:** Core platform migration and voice runtime are in place (Tauri v2 + Swift helper), while wake-word quality still depends on replacing the temporary text-matching fallback with a trained CoreML model.
- **Priority note:** Live Talk wake-word model work is intentionally deferred while other product features are prioritized.

## Start Here By Task

### Routing and model behavior
- `src/agent/nodes/router.py`
- `src/agent/llm.py`
- `src/agent/swap_manager.py`
- `src/agent/nodes/complex.py`
- Tests:
  - `tests/test_router_model_swap.py`
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
- Rebuild canonical handoff: `docs/AI_REBUILD_MASTER_PLAN.md`
- Multi-agent resume protocol: `docs/AI_MULTI_AGENT_RESUME_PLAYBOOK.md`
- API contract: `docs/API_REFERENCE.md`
- WebSocket contract: `docs/CHAT_PROTOCOL.md`
- Active status and risks: `docs/STATUS.md`
- Architecture decisions: `docs/ADR.md`
- ObjC FFI crash analysis: `docs/OBJC_FFI_CRASH.md`
- SoundAnalysis + WhisperKit migration plan: `docs/SOUNDANALYSIS_WAKEWORD_ARCHITECTURE.md`
- Live Talk voice processing, Rust VAD, and roadmap (AEC / next steps): `docs/LIVE_TALK_VOICE_PROCESSING_AND_VAD.md`
- Live Talk Whisper filler hallucinations & forced-finalization: `docs/LIVE_TALK_WHISPER_FILLER_AND_FORCE_FINALIZE.md`
- Athena CoreML training guide: `docs/COREML_ATHENA_MODEL_GUIDE.md`
- Linear workflow (issue/PR conventions): `docs/LINEAR_WORKFLOW.md`
- Performance & memory SLOs: `docs/PERFORMANCE_SLOS.md`

## Before You Commit (Agent Checklist)

1. Scope changes to one risk/theme.
2. Update tests in the touched area.
3. Verify behavior with targeted test runs.
4. Update docs when API/WS behavior changes.
5. Confirm `docs/STATUS.md` still reflects current risk state.
