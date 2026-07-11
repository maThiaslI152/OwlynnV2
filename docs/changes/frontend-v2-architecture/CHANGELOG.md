# Frontend V2 Architecture & Tailwind Migration Changelog

## 2026-07-12 — Frontend architectural refactor, Tailwind integration, and Voice Interaction

### What
- **Tailwind CSS Integration**: Successfully migrated to `@tailwindcss/postcss` for robust styling without heavy dependencies. Configured `tailwind.config.js` to preserve the glassmorphic aesthetics while enabling utility classes.
- **Component Restructuring**: Organized all flat `.tsx` files in `frontend-v2/src/components` into domain-specific directories (`layout/`, `chat/`, `pentest/`, `study/`, `shared/`) for improved maintainability. Fixed all relative imports.
- **Data Connectors UI**: Replaced custom file drag-and-drop logic in `Composer.tsx` with `react-dropzone` for better robustness. Added `DataConnectorsPanel.tsx` in a tabbed Settings UI to configure external integrations like GitHub and Confluence.
- **Global Modal Management**: Implemented `useModalStore.ts` using Zustand to track modal state globally and `ModalManager.tsx` to handle animations, accessibility (ESC to close), and proper z-indexing.
- **Voice Interaction**: Added real-time dictate functionality using the native Web Speech API (`SpeechRecognition`) in `Composer.tsx`, and a text-to-speech button (`speechSynthesis`) to agent messages in `ActivityFeed.tsx`.
- **i18n Support**: Installed and configured `react-i18next` for internationalization.
- **Phase 1: API SDK Layer**: Created `frontend-v2/src/sdk/index.ts` to abstract `fetch` calls. Refactored Study dashboards/analytics to use `StudyAPI` instead of raw fetches.
- **Phase 2: Optimistic UI Pipeline**: Decoupled the WebSocket dispatch in `frontend-v2/src/App.tsx`. `handleSend` now appends a `pending` message to the store, and a new decoupled `useEffect` monitors for pending messages to trigger the WS transmission. Added `status: 'pending' | 'sent'` to `ChatMessage` in `protocol.ts`.
- **Phase 3: Transient Event Bus**: Created `frontend-v2/src/lib/eventBus.ts` for transient event dispatches (like `FOCUS_COMPOSER` and `CLEAR_ATTACHMENTS`) to prevent prop-drilling, and integrated it into `Composer.tsx`.

### Why
- The flat structure of `frontend-v2/src/components` containing nearly 50 components was becoming unmaintainable and difficult to navigate.
- The monolithic `index.css` was growing out of control; transitioning to Tailwind CSS standardizes styling, enables consistency across UI elements, and reduces raw CSS bundle size.
- A standardized Modal Manager resolves overlapping z-index bugs and creates a more robust accessibility story.
- Voice Interaction and Data Connectors are key features for parity with other advanced LLM UIs (e.g. AnythingLLM).
- To abstract fetch calls, decouple WebSocket dispatches to enable optimistic UI updates, and reduce prop-drilling via an event bus.

### Files Modified
- `frontend-v2/package.json`
- `frontend-v2/tailwind.config.js` [NEW]
- `frontend-v2/postcss.config.js`
- `frontend-v2/src/index.css`
- `frontend-v2/src/App.tsx`
- `frontend-v2/src/main.tsx`
- `frontend-v2/src/components/**/*.tsx` (Moved and modified)
- `frontend-v2/src/components/shared/DataConnectorsPanel.tsx` [NEW]
- `frontend-v2/src/components/layout/ModalManager.tsx` [NEW]
- `frontend-v2/src/state/useModalStore.ts` [NEW]
- `frontend-v2/src/i18n.ts` [NEW]
- `frontend-v2/src/sdk/index.ts` [NEW]
- `frontend-v2/src/lib/eventBus.ts` [NEW]
- `frontend-v2/src/types/protocol.ts`
