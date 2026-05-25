---
last_verified: 2026-05-26
auto_generated: false
---

# Frontend V2 (React + TypeScript)

## Overview

Active Owlynn frontend. Provides the app shell, chat UX, workspace/project switching, and inspector panels used by the FastAPI + WebSocket backend.

## Entry Points

```text
frontend-v2/src/App.tsx                       # React app shell, WebSocket lifecycle
frontend-v2/src/components/AppShell.tsx        # Shell layout, sidebar
frontend-v2/src/state/useAppStore.ts           # Zustand store
frontend-v2/src/lib/wsClient.ts               # WebSocket client
frontend-v2/src/lib/tauriBridge.ts             # Tauri IPC bridge
frontend-v2/src/appEventHandlers.ts            # Project-switch thread resolution
```

## Architecture

| Component | Role |
|-----------|------|
| `AppShell` | Shell layout, sidebar Workspace and Chat sections |
| `Composer` | Message input with file attachments |
| `OrchestrationPanel` | Routing decisions (route, model, confidence) |
| `SafeModePanel` | Safety level and execution policy controls |
| `ScreenAssistPanel` | Screen capture, preview, annotation |
| `ToolExecutionPanel` | Tool call logs with HMAC audit trail |
| `ActionProposalQueue` | Pending security approvals |
| `ProjectKnowledgePanel` | Indexed knowledge files per project |

## Flow

### Workspace CRUD

Workspace CRUD implemented with inline actions in the left sidebar Workspace list:

| Action | Trigger | API Call |
|--------|---------|----------|
| Create | `+ New` opens inline name input, Enter/blur saves | `POST /api/projects` |
| Rename | Pencil action on non-default workspace row | `PUT /api/projects/{id}` |
| Delete | `X` action on non-default workspace row with confirmation | `DELETE /api/projects/{id}` |
| Refresh | `Refresh` in Workspace header | `GET /api/projects` |

Create flow uses inline input pattern (same as rename), not `window.prompt`.

### Thread and Chat Isolation

| Rule | Behavior |
|------|----------|
| Workspace creation | Mints fresh thread id (`thread-<uuid>`) |
| Workspace switch | Restores that workspace's current thread |
| Active workspace deletion | Switches to `default` using existing thread (or new one if missing) |
| New workspace chat list | Initially empty; first user message lazily registers first chat |

Per-project thread mapping via `projectThreadsRef`. STM/LTM and chat history boundaries aligned with workspace context.

### Memory Management UI

`MemoryPanel` (`src/components/MemoryPanel.tsx`) displays three sections:

| Section | Source | Behavior |
|---------|--------|----------|
| Tracked Topics & Interests | `GET /api/topics`, `GET /api/interests` | Auto-refresh on `memory_updated` WS event |
| Long-Term Memories | `GET /api/mem0/search` | Searchable, deletable list. Delete (×) button calls `POST /api/mem0/delete`. Memory count in header. Auto-refresh on `memory_updated` |
| Prompt Context | `GET /api/memory-context` | Expandable view of full memory context injected into LLM system prompt |

All interactive elements inside Memory Panel use `e.stopPropagation()` to prevent parent `CollapsibleSection` toggle. Delete (×) button has 24×22px hit area.

## API

### Mem0 Endpoints (Backend)

Added to `src/api/server.py`:

| Endpoint | Description |
|----------|-------------|
| `GET /api/mem0/search?query=&limit=50&project_id=` | Search vector memories |
| `GET /api/mem0/count?project_id=` | Count memories |
| `POST /api/mem0/delete` | Delete memory by ID |
| `POST /api/mem0/clear` | Clear all memories for a user |
| `POST /api/mem0/reset` | Reset all memories (global) |

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Inline CRUD (not prompts) | More reliable in browser automation and desktop runtime | More complex UI logic |
| Per-project thread mapping | STM/LTM isolation by workspace | Additional state management |
| Zustand for all frontend state | Simple, no middleware nesting | Single store grows large |
| `default` workspace protected from deletion | Always have a fallback workspace | Less flexibility |

## Testing

```bash
cd frontend-v2
npm install
npm run dev
npm run build
npx vitest run
```

Current: 50 passed, build passes.

## Configuration

| Rule | Detail |
|------|--------|
| `default` workspace | Protected from deletion in backend, hidden from delete action in frontend |
| Workspace UI | Written for v2 patterns, does not reuse legacy frontend implementation |
| `src/index.css` | Shared styles for workspace/chat row actions |
