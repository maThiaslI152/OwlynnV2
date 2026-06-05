---
status: active
category: guide
last_updated: 2026-05-31
owner: human
---

# Owlynn SOTA Features Guide: Bridging Competitive Gaps

> **Purpose:** Implementation guide for state-of-the-art features bridging competitive gaps.

**Date:** 2026-05-27  
**Status:** Implementation Complete & Verified (Full-Stack Browser Test: 2026-05-27 03:00 UTC+7)  
**Last Verified:** Qdrant/Redis up, LM Studio (8 models), all 5 unit tests pass, browser UI fully interactive

This guide details the architecture, code locations, startup instructions, and verification checklists for the three "falling behind" features implemented to bridge the competitive gap with state-of-the-art local AI assistants:
1. **Dynamic Agent Persona Selector UI & State System**
2. **OpenAI-Compatible Local API Server & Streaming CLI**
3. **Automatic Zero-Config Document Indexing (LocalDocs-style RAG)**

---

## 1. Architectural Overview & File Mapping

### A. Dynamic Agent Persona Selector
This feature lets the user switch assistant personas (e.g., Owlynn, Coder, Writer, Researcher) directly inside the composer interface, dynamically adjusting system prompts, allowed tools, and response tones.

*   **Backend Profile Spec**: [src/memory/persona_manager.py](file:///Users/tim/Works/OwlynnV2/src/memory/persona_manager.py)
    *   Defines built-in profiles and custom profile directories under `data/personas/`.
*   **Prompt Injection Nodes**: [src/agent/nodes/memory.py](file:///Users/tim/Works/OwlynnV2/src/agent/nodes/memory.py) & [src/agent/nodes/simple.py](file:///Users/tim/Works/OwlynnV2/src/agent/nodes/simple.py)
    *   Dynamically pulls `persona_id` from the active LangGraph state and shapes system prompt templates.
*   **REST API Endpoints**: [src/api/routes/profile.py](file:///Users/tim/Works/OwlynnV2/src/api/routes/profile.py)
    *   `GET /api/personas` (returns all active personas) & `POST /api/personas` (saves custom profiles).
*   **Frontend Zustand Store**: [frontend-v2/src/state/useAppStore.ts](file:///Users/tim/Works/OwlynnV2/frontend-v2/src/state/useAppStore.ts)
    *   Maintains `activePersonaId` (defaulting to `"default"`) and provides `setActivePersonaId(id)`.
*   **WebSocket Contract**: [frontend-v2/src/types/protocol.ts](file:///Users/tim/Works/OwlynnV2/frontend-v2/src/types/protocol.ts) & [frontend-v2/src/App.tsx](file:///Users/tim/Works/OwlynnV2/frontend-v2/src/App.tsx)
    *   Extends `UserMessageEvent` to support `persona_id` and binds it to outgoing socket messages.
*   **Visual Pill Dropdown Selector**: [frontend-v2/src/components/Composer.tsx](file:///Users/tim/Works/OwlynnV2/frontend-v2/src/components/Composer.tsx)
    *   Implements the dynamically fetched selector pill and card dropdown, complete with a click-outside auto-close hook.
*   **Curated Glassmorphic Styles**: [frontend-v2/src/index.css](file:///Users/tim/Works/OwlynnV2/frontend-v2/src/index.css)
    *   Contains modern styling rules: `backdrop-filter: blur(16px)`, active cyan/blue glows, card lists, hover micro-animations, and entry transitions.

---

### B. OpenAI-Compatible API Server & CLI
Exposes local completions REST endpoints so developers can integrate Owlynn V2 into command-line scripts or IDE code editors (like Cursor or VSCode extensions).

*   **REST endpoint (`POST /v1/chat/completions`)**: [src/api/routes/openai.py](file:///Users/tim/Works/OwlynnV2/src/api/routes/openai.py)
    *   Implements official OpenAI schema mapping, supporting synchronous JSON response and real-time SSE token streaming (`stream=True`).
*   **Security Gating Bypasses**: [src/agent/nodes/security_proxy.py](file:///Users/tim/Works/OwlynnV2/src/agent/nodes/security_proxy.py)
    *   Automatically handles sensitive tools in API mode according to the `auto_approve_sensitive` client payload flag, bypassing visual HITL blocks.
*   **Click-Based Command Line Tool**: [src/cli.py](file:///Users/tim/Works/OwlynnV2/src/cli.py)
    *   Enables terminal actions: `query`, `stream`, and `status`.

---

### C. Zero-Config Workspace RAG Indexer
Automatically watches local project directories, indexes new documents, generates embeddings, and retrieves relevant chunks using hybrid search.

*   **Directory Watcher & Indexer callback**: [src/api/file_processor.py](file:///Users/tim/Works/OwlynnV2/src/api/file_processor.py) & [src/api/routes/files.py](file:///Users/tim/Works/OwlynnV2/src/api/routes/files.py)
    *   Catches added/modified files in the active workspace directory, splits text into 1500-char chunks (with 200-char overlap), and auto-indexes vectors to Qdrant collection.
*   **LM Studio Embeddings Wrapper**: [src/api/routes/](file:///Users/tim/Works/OwlynnV2/src/api/routes/)
    *   Calls local embedding endpoint `/v1/embeddings` (using `nomic-embed-text-v1.5`) to optimize VRAM and memory footprints.
*   **Retriever Tool**: [src/tools/rag_tools.py](file:///Users/tim/Works/OwlynnV2/src/tools/rag_tools.py) & [src/agent/tool_sets.py](file:///Users/tim/Works/OwlynnV2/src/agent/tool_sets.py)
    *   Exposes `@tool` `search_workspace_docs` to LangGraph sessions, performing project-isolated semantic hybrid search on Qdrant.

---

## 2. Startup Guide (Step-by-Step)

To run the full multi-process application locally, follow these steps:

### Step 1: Pre-requisites
1.  **LM Studio (Local LLM Server):**
    *   Open **LM Studio**.
    *   Start the Local Server on port **`1234`**.
    *   Ensure your embedding model (`nomic-embed-text-v1.5` or equivalent) and reasoning LLM (`gemma-4` or equivalent) are loaded.
2.  **Containers:**
    *   Verify that your Qdrant and Redis container engines are active.

### Step 2: Launch Owlynn Services
Run the launcher script from the root directory:
```bash
./start.sh
```
This launcher automatically:
1.  Verifies Qdrant & Redis containers are active.
2.  Validates that LM Studio local server responds on port `1234`.
3.  Clears stale ports, activates the python virtual environment, and starts the FastAPI Uvicorn backend on port `8000`.
4.  Launches the Vite React frontend development server on port `5173`.
5.  Builds the local Swift audio helper and launches the Tauri debug `.app` bundle.

*(Alternatively, if running headless in a remote container, start the backend directly)*:
```bash
export PYTHONPATH="$(pwd):$PYTHONPATH"
source .venv/bin/activate
uvicorn src.api.server:app --host 127.0.0.1 --port 8000
```

---

## 3. Core Verification Procedures

Ensure all updates run successfully by executing the following validation checklists:

### A. Run Automated Unit Tests (Fast & Standalone)
Verify the core persona manager specifications using pytest:
```bash
.venv/bin/python -m pytest tests/test_falling_behind_features.py
```
👉 **Expected Output:**
```text
tests/test_falling_behind_features.py .....                              [100%]
========================= 5 passed in 0.06s =========================
```

### B. Verify the Dynamic Persona UI
1.  Launch the application using `./start.sh` or navigate to `http://127.0.0.1:5173` in a web browser.
2.  Note the new glassmorphic pill element right above the input textbox inside the Composer panel (showing **🤖 Owlynn General Workspace Assistant ▼**).
3.  Click the pill. The glassmorphic panel will transition into view, displaying available built-in personas, their descriptions, and tones.
4.  Choose **Owlynn Coder** (expert technical lead).
5.  Type *"How do you write a quicksort in python?"* and submit.
    *   👉 **Expected Behavior:** The response should incorporate technical instructions, displaying dry, direct code templates.
6.  Switch the persona to **Owlynn Editor** (creative writing coach) and submit a new message.
    *   👉 **Expected Behavior:** The agent response tone dynamically transitions to supportive, literary, and articulate.
7.  Click anywhere outside the dropdown and verify that the dropdown panel auto-closes cleanly.

### C. Verify OpenAI REST Completions SSE Streaming
Query the streaming Completions endpoint directly using the click CLI tool:
```bash
.venv/bin/python src/cli.py stream "Briefly explain the benefit of local vector databases."
```
👉 **Expected Behavior:** Token chunks will stream in real-time right into your standard terminal output, finishing with a final newline once the SSE `[DONE]` protocol block is resolved.

### D. Verify Zero-Config Document indexing (RAG)
1.  Start your Owlynn services.
2.  Open your active workspace directory.
3.  Drop a test text or markdown file inside (e.g., `features_list.txt` containing unique, arbitrary text like *"Secret project code: OWLYNN-BETA-99"*).
4.  Check uvicorn backend terminal outputs.
    *   👉 **Expected Behavior:** Logs should print file watcher auto-triggers:
        ```text
        [Watcher] File created: /Users/.../workspace/features_list.txt
        [Watcher] Processing features_list.txt (.txt)...
        [Watcher] Successfully processed features_list.txt
        ```
    *   Vector indexing to Qdrant occurs asynchronously after processing — watch for `Inserting N vectors into collection` in backend logs.
5.  Ask Owlynn in your active chat window:
    *"What is the secret project code?"*
    *   👉 **Expected Behavior:** Owlynn calls memory retrieval tools (`recall_all_memories` / `search_workspace_docs`), queries the Qdrant vector store, and returns the correct code (*OWLYNN-BETA-99*). Backend logs will show `Inserting N vectors into collection` and `points/query` operations.

---

## 4. Known Issues & Test Notes

### Router 1b Model Stability
The `ibm-grok4-ultrafast-coder-1b` classifier model can fail on certain queries with a `node_error` event in the router node. The medium reasoning model (`gemma-4-e4b-uncensored-hauhaucs-aggressive`) handles these cases reliably. When the 1b router fails, the agent graph may produce an empty response via the CLI streaming endpoint. The frontend WebSocket path includes HITL fallback prompts that allow the user to clarify intent when router confidence is low.

### HITL Gate Behavior
The execution policy defaults to `hitl` (manual approval). For smoother testing, switch to `auto_approve` via the Execution Policy dropdown in the Safe Mode panel, or pass `--approve-sensitive` to the CLI. Without this, skill ambiguity prompts will block the conversation flow.

### Workspace File Path
The file watcher monitors the `workspace/` directory relative to the project root. Files dropped outside this directory are not auto-indexed. The Knowledge panel in the frontend shows "No knowledge files indexed" until files are placed in the correct location.

### Reference: Verified Environment (2026-05-27)
- **Qdrant:** `qdrant/qdrant:latest` on port 6333
- **Redis:** `redis/redis-stack-server:latest` on port 6379
- **LM Studio models:** `nomic-embed-text-v1.5`, `gemma-4-e4b`, `ibm-grok4-ultrafast-coder-1b`, plus 5 others
- **Backend:** Python 3.14.3, uvicorn on port 8000
- **Frontend:** Vite 8.0.10 on port 5173, React 19.2.5

## Related

- [`docs/README.md`](README.md) — project documentation map
- [`docs/PROJECT_GUIDE.md`](PROJECT_GUIDE.md) — navigation index

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter, purpose blockquote
