## 2026-07-10 — Phase 1 and 4 Roadmap Completion

### What
- Fixed HITL bypass by routing internal tool calls through the main `security_proxy_node`.
- Switched Fernet master key storage to use the macOS Keychain (`security` command) instead of plaintext files.
- Fixed Unicode regex bug (using `re.UNICODE`) in memory manager.
- Fixed podman to docker call in pentest tools.
- Created semantic tool reranking using Nomic embeddings, connected to complex LLM node.
- Upgraded memory extraction worker to an Observer/Reflector 2-phase LLM pipeline for deduplication.
- Created and registered new data connectors: `ingest_github_repo`, `ingest_youtube_transcript`, `ingest_obsidian_vault`.
- Deduplicated `SENSITIVE_TOOLS` in `security_proxy_node`, importing from hitl policy.
- Raised memory cap to 24000.
- Built APScheduler wrapper and REST API for autonomous background jobs.
- Hooked up scheduled jobs, config, and export APIs to the main server.
- Built new Settings UI and config API.
- Built new Citations UI.
- Built Chat export API.
- Added drag-and-drop session context functionality to the Composer.

### Why
To complete the Phase 1 and Phase 4 roadmap goals, providing better security, background jobs, tool reranking, UI enhancements (Settings, Citations, Composer), and reliable integrations.

### Files
- `src/agent/pentest/executor.py`
- `src/memory/pentest_engagement.py` / `src/config/engagement_crypto.py`
- `src/memory/memory_manager.py`
- `src/tools/pentest_tools.py`
- `src/agent/tool_reranker.py` / `src/agent/core/complex.py`
- `src/memory/extraction/worker.py`
- `src/tools/data_connectors.py` / `src/agent/tool_sets.py`
- `src/agent/nodes/security_proxy.py` / `src/agent/hitl/policy.py`
- `src/agent/nodes/memory.py`
- `src/api/scheduler_manager.py` / `src/api/routes/scheduled_jobs.py` / `src/api/server.py`
- `src/api/routes/config.py` / `src/api/routes/export.py`
- `frontend-v2/src/components/SettingsPanel.tsx`
- `frontend-v2/src/components/CitationsList.tsx`
- `frontend-v2/src/components/Composer.tsx`
