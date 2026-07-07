---
status: active
category: changelog
last_updated: 2026-07-07
owner: ai-agent
audience: human
---

# Electron Packaging — 2026-07-07

## Summary

Owlynn is now available as a native macOS `.app` (v0.1.1). The Electron app spawns the Python backend, starts containers, shows a splash screen during initialization, and supports close-to-background with a system tray.

## Changes

### New Files

| File | Purpose |
|------|---------|
| `frontend-v2/electron-builder.yml` | macOS packaging config (appId, entitlements, permission descriptions, extraResources) |
| `frontend-v2/electron/entitlements.mac.plist` | Apple Events entitlement for osascript calls |
| `frontend-v2/electron/splash.html` | Loading screen — 4-step status (containers → LM Studio → backend → AI) |
| `frontend-v2/src/vite-env.d.ts` | TypeScript declaration for `__APP_VERSION__` |
| `docs/guides/app-release.md` | Full release guide |

### Modified Files

| File | Changes |
|------|---------|
| `frontend-v2/package.json` | Version `0.1.1` |
| `frontend-v2/vite.config.ts` | `define: { __APP_VERSION__: JSON.stringify(pkg.version) }` |
| `frontend-v2/electron/main.ts` | **Full rewrite** — splash screen, backend spawning, container startup, tray, close-to-background, graceful shutdown, `findUvPath()` for packaged app |
| `frontend-v2/electron/preload.ts` | Added IPC channels: `get_app_version`, `hide_to_tray`, `get_extension_path`, `open_extension_folder`, `splash-status` |
| `frontend-v2/src/lib/electronBridge.ts` | Added: `getAppVersion()`, `hideToTray()`, `getBrowserExtensionPath()`, `openExtensionFolder()` |
| `frontend-v2/src/components/MacMenuBar.tsx` | "About Owlynn" (toast with version), "Hide Owlynn", "Quit Owlynn" wired to IPC |
| `frontend-v2/src/components/AppShell.tsx` | Version footer pinned at bottom of left sidebar |
| `src/memory/user_profile.py` | Atomic writes (temp+rename) — prevents corruption on crash |
| `src/config/secret_store.py` | Atomic writes (temp+rename) — prevents corruption on crash |
| `start.sh` | Writes `~/.owlynn/config.json` with project root on first run |
| `docs/STATUS.md` | Added packaging, atomic writes, hotfix entries |
| `AGENTS.md` | Added "Package Electron app" to task routing |

## Packaging Fixes (v0.1.1)

### Fix 1: `uv` Binary Not Found (spawn uv ENOENT)

**Problem:** Packaged `.app` doesn't inherit the user's shell PATH. `spawn('uv', ...)` fails with ENOENT because `/opt/homebrew/bin/` and `~/.cargo/bin/` aren't in the app's PATH.

**Fix:** Added `findUvPath()` in `electron/main.ts` that checks common install locations before spawning. Falls back to PATH lookup for dev mode.

### Fix 2: splash.html Not in Bundle

**Problem:** `vite-plugin-electron` only compiles `main.ts` and `preload.ts`. The `splash.html` file wasn't copied to the `.app` bundle.

**Fix:** Added `electron/splash.html` to `extraResources` in `electron-builder.yml`. Splash window checks both packaged and dev locations.

### Fix 3: YAML Syntax Error in electron-builder.yml

**Problem:** Missing closing quote on `to: "splash.html` caused YAML parse error during build.

**Fix:** Corrected to `to: "splash.html"`.

### Fix 4: Splash Screen Stuck (IPC Event Argument Mismatch)

**Problem:** Splash screen showed all steps stuck on pending. The `splash-status` IPC listener used `(_event, data)` but the preload's `contextBridge.on()` strips the event argument, so `data` was `undefined`.

**Fix:** Changed listener to `(data)` in `splash.html`.

### Fix 5: Splash Messages Sent Before Window Loaded

**Problem:** `createSplashWindow()` called `loadFile()` without awaiting. `sendSplash()` fired before the splash HTML loaded and the IPC listener registered.

**Fix:** `createSplashWindow()` returns a `Promise<void>` that resolves on `did-finish-load`. Startup flow awaits it before sending IPC.

### Fix 6: Backend Crash Silent — App Loads But Nothing Works

**Problem:** `spawnBackend()` was fire-and-forget. If backend crashed, main window loaded but all API calls failed silently.

**Fix:** Crash detection (reject if exit within 2s), stderr forwarded to splash hint, stay on splash on failure instead of transitioning to broken main window.

### Fix 7: Duplicate Containers Conflict

**Problem:** Both `start.sh` and the Electron app tried to start the same containers. Conflicts when containers already exist.

**Fix:** `startContainers()` checks if containers are already running before starting. Both share the same containers.

### Fix 8: Port Conflict After Backend Kill

**Problem:** `killStaleBackend()` didn't wait for port 8000 to be released. New backend could fail with "address already in use".

**Fix:** Polls `lsof` until port is free (up to 5s) before spawning.

### Fix 9: Health Check False Positive

**Problem:** `waitForHealth()` passed on first "ready" response. Could pass on stale backend (SIGKILL is async).

**Fix:** Requires 2 consecutive "ready" responses (2s apart).

### Fix 10: Splash Flashes Briefly

**Problem:** Startup completes in ~3s when all services already running. Splash flashes too fast.

**Fix:** Minimum 3-second splash display time.

## Architecture

```
Owlynn.app (Electron)
  ├─ Splash window (splash.html — loading status)
  ├─ Main window (http://127.0.0.1:8000/ — backend serves frontend)
  ├─ Tray icon (menu bar — Show/Quit)
  ├─ Spawns backend process (uvicorn on :8000)
  └─ Bundles browser-extension/ in Contents/Resources/

Startup: config.json → containers → LM Studio → backend spawn → health poll → main window
Shutdown: SIGTERM backend → wait 5s → SIGKILL → remove PID file
Close: X button hides window (backend runs), Cmd+Q quits (backend stops)
```

## Related

- [`docs/guides/app-release.md`](../guides/app-release.md) — full release guide
- [`docs/STATUS.md`](../STATUS.md) — project status tracker
