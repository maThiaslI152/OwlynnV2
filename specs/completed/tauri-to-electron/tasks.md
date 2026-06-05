# Tasks: Tauri to Electron Migration

> **Purpose:** Break down the design into executable steps. Written in Plan mode after design. Must be approved via AskQuestion `tasks-review` popup before implementation.

## Phase 1: Dependency & Scaffold Migration

- **1. Delete Tauri Backend**
  - **files:** `src-tauri/`
  - **maps_to:** N/A (Cleanup)
  - **verify_steps:**
    1. Ensure `src-tauri` is completely deleted.

- **2. Setup Electron Dependencies & Vite Config**
  - **files:** `frontend-v2/package.json`, `frontend-v2/vite.config.ts`
  - **maps_to:** AC-1, AC-5
  - **verify_steps:**
    1. `npm install` runs successfully.
    2. `package.json` contains `main`, `electron`, `electron-builder`, and `vite-plugin-electron`.

- **3. Create Electron Main Process & Preload**
  - **files:** `frontend-v2/electron/main.ts`, `frontend-v2/electron/preload.ts`, `frontend-v2/tsconfig.node.json`
  - **maps_to:** AC-1, AC-4
  - **verify_steps:**
    1. Verify `main.ts` correctly creates a `BrowserWindow` and handles `set_window_size` IPC.
    2. Verify `preload.ts` exposes `window.electronAPI`.

## Phase 2: Frontend Bridge Porting

- **4. Refactor TauriBridge to ElectronBridge**
  - **files:** `frontend-v2/src/lib/tauriBridge.ts` -> `frontend-v2/src/lib/electronBridge.ts`, `frontend-v2/src/App.tsx` (and other UI consumers)
  - **maps_to:** AC-3, AC-4
  - **verify_steps:**
    1. Verify `electronBridge.ts` compiles without type errors.
    2. Verify `electronBridge` intercepts `speakText`, `startScreenPreview`, etc.

## Phase 3: Hardware Porting (Node/Web APIs)

- **5. Implement Screen Assist Capture**
  - **files:** `frontend-v2/electron/main.ts`
  - **maps_to:** AC-3
  - **verify_steps:**
    1. Verify `ipcMain.handle('start_screen_preview')` runs `screencapture -x -t jpg` and returns the valid path.

- **6. Migrate TTS to Web Speech API**
  - **files:** `frontend-v2/src/lib/electronBridge.ts`
  - **maps_to:** AC-2
  - **verify_steps:**
    1. Verify `electronBridge.speakText` invokes `window.speechSynthesis.speak()`.

## Approval

- `tasks-review` AskQuestion: approved
