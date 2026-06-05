# Tauri to Electron Migration Guide

> **Purpose:** Detailed step-by-step migration guide mapping out what changes are happening and why.

## 1. Dependency Transition

| Feature | Old (Tauri) | New (Electron) | Action Required |
|---------|-------------|----------------|-----------------|
| IPC Interface | `@tauri-apps/api/core` | `window.electronAPI` | Uninstall Tauri API package. Define TypeScript interface for `window.electronAPI` in frontend. |
| Build Pipeline | `tauri-cli` | `electron-builder` + `vite-plugin-electron` | Remove `src-tauri` folder. Add plugins to `vite.config.ts`. Update npm scripts (`dev`, `build`). |

## 2. API Bridging

The existing `tauriBridge.ts` abstracts away the backend wrapper from the React components. This file will be renamed to `electronBridge.ts`.

**Changes inside the bridge:**
- Remove `loadTauriCore()`.
- Check for `window.electronAPI !== undefined`.
- `invokeOrResult` will directly call `window.electronAPI.invoke(command, args)`.

*Because we are preserving the `BridgeResult<T>` wrapper, zero changes are required in `App.tsx` or any React components that consume these APIs.*

## 3. Node/System Feature Porting

| Feature | Tauri Implementation (`main.rs`) | Electron Implementation (`main.ts`) |
|---------|----------------------------------|-------------------------------------|
| Safe Mode State | Native Rust `Mutex` state | In-memory variables in Node main process |
| TTS | Rust `std::process::Command` | **Migrated to Web Speech API** (executed natively in Chromium renderer via `speechSynthesis`, skipping IPC entirely) |
| Screen Capture | `screencapture -x -t jpg` | Node.js `child_process.exec('screencapture ...')` |
| Window Resizing | Tauri `set_size` | Electron `BrowserWindow.setContentSize` |
| Action Proposals | Rust tracking & IPC emit | Node tracking & `webContents.send` emit |

## 4. Rollout Strategy

1. **Delete** `src-tauri`.
2. **Install** Electron dev dependencies.
3. **Scaffold** `electron/main.ts` and `electron/preload.ts`.
4. **Implement** IPC listeners in `main.ts`.
5. **Update** `tauriBridge.ts` -> `electronBridge.ts` and modify UI imports.
6. **Migrate** TTS from IPC invoke to native `window.speechSynthesis`.
7. **Test** the build locally.
