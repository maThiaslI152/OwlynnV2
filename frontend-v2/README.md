# Frontend V2 (React + TypeScript)

`frontend-v2` is the active Owlynn frontend. It provides the app shell, chat UX, workspace/project switching, and inspector panels used by the FastAPI + WebSocket backend.

## Run and Build

```bash
cd frontend-v2
npm install
npm run dev
```

Production build:

```bash
npm run build
```

## Workspace CRUD (Option A)

Workspace CRUD is implemented with inline actions in the left sidebar Workspace list.

- Create: `+ New` opens an inline name input row in the Workspace list, then Enter/blur saves
- Rename: pencil action on each non-default workspace row
- Delete: `X` action on each non-default workspace row with confirmation
- Refresh: `Refresh` in the Workspace header

### API Mapping

- `POST /api/projects` -> create workspace
- `PUT /api/projects/{id}` -> rename workspace
- `DELETE /api/projects/{id}` -> delete workspace
- `GET /api/projects` -> refresh workspace and chat lists

No backend changes are required for this frontend flow.

### Create Flow Details

- Workspace creation does not use browser-native `window.prompt`.
- The UI uses the same inline input pattern used for rename, which is more reliable in browser automation and desktop runtime.
- Save action triggers `POST /api/projects`, then auto-switches to the new workspace with a fresh thread id.

### Thread and Chat Isolation Rules

Workspace session separation is preserved with per-project thread mapping (`projectThreadsRef`):

- Creating a workspace mints a fresh thread id (`thread-<uuid>`)
- Switching workspace restores that workspace's current thread
- Deleting the active workspace switches to `default` using its existing thread (or a new one if missing)
- New workspace chat list is initially empty; first user message lazily registers the first chat in backend

This keeps STM/LTM and chat history boundaries aligned with workspace context.

## Memory Management UI

The Memory Panel (`src/components/MemoryPanel.tsx`) displays three sections:

1. **Tracked Topics & Interests** — from `/api/topics` and `/api/interests` (personal assistant data). Auto-refreshes when `memory_updated` WebSocket event fires.

2. **Long-Term Memories** — from `/api/mem0/search`. Shows a searchable, deletable list of Mem0/Qdrant memories. Features:
   - Search input filters memories by semantic query
   - Each memory has a delete (x) button that calls `/api/mem0/delete`
   - Memory count displayed in the section header
   - Auto-refreshes on `memory_updated` WebSocket event

3. **Prompt Context** — from `/api/memory-context`. Expandable view showing the full memory context injected into the LLM system prompt.

### Key Files for Memory UI

- `src/components/MemoryPanel.tsx`: main memory display component
- `src/index.css`: styles for memory search input, memory list items, and delete buttons

### Click Interception Fix (Memory Panel Buttons)

All interactive elements inside the Memory Panel (Show/Hide toggles, Search, Clear, Delete × buttons) use `e.stopPropagation()` to prevent the parent `CollapsibleSection` header click handler from toggling the section open/closed. This ensures that clicking any button inside the Memory & Context inspector section only triggers its own action, not the section collapse.

The delete (x) button was also updated with an increased click target:
```
Before: padding: 0 2px, font-size: 0.85rem → 11x13px hit area
After:  padding: 4px 8px, font-size: 0.95rem → 24x22px hit area
```

## Mem0 API (Backend)

New endpoints added to `src/api/server.py`:

- `GET /api/mem0/search?query=&limit=50&project_id=` — search vector memories
- `GET /api/mem0/count?project_id=` — count memories
- `POST /api/mem0/delete` — delete memory by ID
- `POST /api/mem0/clear` — clear all memories for a user
- `POST /api/mem0/reset` — reset all memories (global)

## Live Talk (Tauri Runtime)

Live Talk uses Tauri runtime commands and events (not browser Web Speech APIs):

- Controls: `src/components/LiveTalkControls.tsx`
- Runtime bridge: `src/lib/tauriBridge.ts`
- Event handling / WS relay: `src/App.tsx`
- Voice store state: `src/state/useAppStore.ts`

### Runtime Commands

- `start_voice_listening` / `stop_voice_listening`
- `get_wake_word_phrase` (fixed to `Athena`)
- `hard_stop_voice`
- `speak_text`

### Runtime Events

- `voice.state`
- `voice.transcript`
- `voice.wake_word`
- `voice.error`
- `voice.tts_state`
- `voice.started`

Final transcript events are converted to normal chat payloads (`type: "user.message"`) with `source: "voice"` so the backend graph processes voice and typed inputs through the same route.

## Key Files

- `src/App.tsx`: project loading, workspace/chat handlers, WebSocket lifecycle
- `src/components/AppShell.tsx`: shell layout, sidebar Workspace and Chat sections
- `src/index.css`: shared styles for workspace/chat row actions
- `src/appEventHandlers.ts`: project-switch thread resolution utilities

## Notes

- `default` workspace is protected from deletion in backend and hidden from delete action in frontend.
- Workspace UI is written for v2 patterns and does not reuse legacy frontend implementation.
