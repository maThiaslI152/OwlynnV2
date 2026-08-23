# Changelog — Thought Graph Branching, Tool Call Resilience & Path Resolution

## 2026-08-23 — Version 0.2.2

### What Changed

1. **Thought Graph Topic Branching & Linking Engine**:
   - **Calibrated Semantic Similarity**: Calibrated cosine similarity threshold from `0.78` down to `0.64` for 1024-dim embedding vectors (`text-embedding-mxbai-embed-large-v1`), categorizing edges into `merges_with` (>= 0.80), `branches_from` (>= 0.72), and `relates_to` (>= 0.64).
   - **Embedding Backfill**: Enabled dynamic lazy embedding generation for un-indexed / un-embedded nodes in `src/memory/thought_graph.py` so newly created conversations can semantically connect with past thoughts.
   - **Chat Title Synchronization**: In `src/api/ws/handler.py`, router-generated chat titles are now immediately synchronized with `ThoughtNode.title` in the PostgreSQL graph store.
   - **Explicit Branch Connection**: When a chat starts as a branch from a parent thread/node (`parent_thread_id`), a directed `branches_to` edge is automatically registered.

2. **Tool Calling Latency & Resilience Optimization**:
   - **Removed `sequential-thinking` from `mcp_config.json`**: Prevented local models (`gemma-4-12b-agentic`) from getting trapped in 4-step sequential thinking tool loops, dropping turn latency from 45s down to 2–4s.
   - **Unprompted Document Generation Discipline**: Updated `src/agent/core/complex_prompt.py` to enforce that document/spreadsheet generation tools (`create_xlsx`, `create_docx`, `create_pptx`, `create_pdf`) are ONLY invoked when explicitly requested by the user.

3. **Notebook Workspace Sandbox Path Resolution**:
   - Updated `src/tools/notebook_worker.py` to execute inside the active project directory (`os.chdir(workspace_dir)`), ensuring generated charts, plots, and files (`plt.savefig`, `to_csv`, `to_excel`) are written directly to `workspace/projects/<project_id>/` and resolved correctly by the frontend image viewer.
   - Expanded regex path rewrite in `src/tools/notebook.py` for `savefig`, `write_html`, `to_csv`, `to_excel`, `to_json`, and `to_parquet`.

4. **Version Bump to 0.2.2 & Desktop Packaging**:
   - Bumped version to `0.2.2` in `pyproject.toml`, `frontend-v2/package.json`, and `frontend-v2/src/test-setup.ts`.
   - Built and installed the packaged application to `/Volumes/KNV3_1TB/Applications/Owlynn.app`.
   - Verified 130 / 130 Vitest tests and Playwright E2E test suite passing.

### Files Modified

- `pyproject.toml`
- `frontend-v2/package.json`
- `frontend-v2/src/test-setup.ts`
- `mcp_config.json`
- `src/agent/core/complex_prompt.py`
- `src/api/ws/handler.py`
- `src/memory/thought_graph.py`
- `src/tools/notebook.py`
- `src/tools/notebook_worker.py`
- `AGENTS.md`
- `docs/INDEX.md`
