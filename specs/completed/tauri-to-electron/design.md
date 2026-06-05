# Design: Tauri to Electron Migration

> **Purpose:** Define how the change will be implemented. Written in Plan mode after requirements are approved. Must be approved via AskQuestion `design-review` popup before proceeding to tasks.

## Architecture & Data Flow

- The frontend will be transitioned from a Tauri project to an Electron project.
- A new `electron/main.ts` file will act as the Electron main process, booting the Chromium browser window and serving the Vite development server (in dev mode) or loading the packaged `index.html` (in production).
- A `electron/preload.ts` script will use `contextBridge` to expose `window.electronAPI`.
- `frontend-v2/src/lib/tauriBridge.ts` will be renamed to `electronBridge.ts` and refactored to call `window.electronAPI.invoke` instead of `@tauri-apps/api/core`.

## Component Modifications

### [DELETE] `src-tauri/`
- Completely remove the Rust backend and configuration.

### [MODIFY] `frontend-v2/package.json`
- Add `electron`, `electron-builder`, `vite-plugin-electron`, and `vite-plugin-electron-renderer`.
- Update `scripts` (e.g., `dev` -> `vite`, `build` -> `tsc && vite build && electron-builder`).

### [NEW] `docs/guides/tauri_to_electron_migration.md`
- Detailed step-by-step documentation mapping the old Tauri API usage to the new Electron implementations.

### [NEW] `frontend-v2/electron/main.ts`
- Implement Electron window lifecycle (`app.whenReady()`).
- Implement IPC listeners (`ipcMain.handle`) for:
  - `speak_text`: Spawns native Web Speech API (Wait, Web Speech API runs in the Renderer! So `speak_text` might just be executed natively on the frontend via `speechSynthesis`, skipping IPC entirely. Or if keeping `say` (as agreed upon in Intent Clarification, wait no, they agreed to Web Speech API! "Switch to the native Chromium Web Speech API")).
  - `start_screen_preview`: Uses `child_process.exec` to run macOS `screencapture`.
  - `set_window_size`: Calls `BrowserWindow.setContentSize`.
  - Action Proposals: Tracks state and emits to WebContents via `webContents.send()`.

### [NEW] `frontend-v2/electron/preload.ts`
- Expose `electronAPI` with `invoke(channel, data)` to map to IPC endpoints, and `on(channel, callback)` for server-to-client events.

## Database Schema Changes

N/A

## Security & Performance

- **Context Isolation:** Enabled by default in Electron 12+. Preload script is required to safely bridge IPC without exposing Node integration to the renderer.
- **Node Integration:** Disabled in the Renderer process.

## References

- [`docs/guides/tauri_to_electron_migration.md`](file:///Users/tim/Works/OwlynnV2/docs/guides/tauri_to_electron_migration.md)

## Approval

- `design-review` AskQuestion: approved
