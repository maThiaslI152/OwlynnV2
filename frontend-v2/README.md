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

## Key Files

- `src/App.tsx`: project loading, workspace/chat handlers, WebSocket lifecycle
- `src/components/AppShell.tsx`: shell layout, sidebar Workspace and Chat sections
- `src/index.css`: shared styles for workspace/chat row actions
- `src/appEventHandlers.ts`: project-switch thread resolution utilities

## Notes

- `default` workspace is protected from deletion in backend and hidden from delete action in frontend.
- Workspace UI is written for v2 patterns and does not reuse legacy frontend implementation.
