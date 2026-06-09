---
status: active
category: guide
audience: agent
last_updated: 2026-06-10
owner: ai-agent
---

# Frontend V2 (React + Electron)

> **Purpose:** Active Owlynn UI — chat, workspace switching, inspector panels, WebSocket client.

## Entry Points

```text
frontend-v2/src/App.tsx                 # App shell, WebSocket lifecycle, HITL resume
frontend-v2/src/components/AppShell.tsx # Layout, sidebar
frontend-v2/src/state/useAppStore.ts    # Zustand store
frontend-v2/src/lib/wsClient.ts       # WebSocket client
frontend-v2/src/lib/electronBridge.ts   # Electron IPC (Safe Mode, screen assist)
frontend-v2/electron/main.ts            # Electron main process
frontend-v2/src/types/protocol.ts       # WS event types (mirror CHAT_PROTOCOL.md)
```

## Architecture

| Component | Role |
|-----------|------|
| `AppShell` | Sidebar, workspace + chat lists |
| `Composer` | Message input, attachments |
| `OrchestrationPanel` | Route, model, confidence display |
| `SafeModePanel` | Safety level (requires Electron IPC) |
| `ScreenAssistPanel` | Screen capture / annotation |
| `ActionProposalQueue` | Pending HITL approvals |

## Dev commands

```bash
cd frontend-v2
npm install          # first time
npm run dev          # Vite + Electron with HMR
npx vitest run       # component tests
npm run build        # production + desktop bundle
```

API/WebSocket proxy: Vite dev server (`5173`) → backend (`8000`). See [`docs/CHAT_PROTOCOL.md`](../docs/CHAT_PROTOCOL.md).

## Related

- [`docs/PROJECT_GUIDE.md`](../docs/PROJECT_GUIDE.md) — full file map
- [`docs/guides/dev-startup.md`](../docs/guides/dev-startup.md) — launch stack

## Last updated

2026-06-10 — agent-first overhaul; electronBridge replaces tauriBridge
