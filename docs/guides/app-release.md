---
status: active
category: guide
last_updated: 2026-07-07
owner: ai-agent
audience: human
---

# Owlynn App Release Guide

> **Purpose:** How to build, distribute, install, and troubleshoot the packaged Owlynn Electron app.

## Prerequisites (User's Machine)

| Requirement | Why | Check |
|-------------|-----|-------|
| macOS 13+ (Ventura) | Electron 42, Apple Virtualization Framework | `sw_vers` |
| LM Studio | Local LLM inference on port 1234 | Must be running with a loaded model |
| Podman Desktop or Docker Desktop | Container runtime for Qdrant + Redis | `podman --version` or `docker --version` |
| uv | Python package manager | `uv --version` |
| Python 3.11+ | Backend runtime | `python3 --version` |
| Brave Browser | Browser extension integration | Must be installed |
| FileVault (recommended) | Full-disk encryption for data at rest | System Settings > Privacy |

## First-Time Setup

1. **Install LM Studio** — download from [lmstudio.ai](https://lmstudio.ai), load a model (default: `qwen3-vl-4b`)
2. **Install Podman Desktop** — download from [podman-desktop.io](https://podman-desktop.io) (or Docker Desktop)
3. **Install uv** — `curl -LsSf https://astral.sh/uv/install.sh | sh`
4. **Clone the repo** — `git clone <repo-url> && cd OwlynnV2`
5. **Run setup** — `./setup.sh` (installs Python deps, downloads Docling models)
6. **Run start.sh once** — `./start.sh` (writes `~/.owlynn/config.json`, starts containers)
7. **Build the app** — `cd frontend-v2 && npm run build`
8. **Install** — drag `frontend-v2/release/Owlynn-0.1.4.dmg` to `/Applications`
9. **Launch** — double-click Owlynn.app in `/Applications`

## What Happens on Launch

```
Owlynn.app double-clicked
  │
  ├─ Read ~/.owlynn/config.json → get project root
  ├─ Start containers: podman compose up -d qdrant redis
  ├─ Check LM Studio :1234 (prompt if not running)
  ├─ Kill stale backend (check ~/.owlynn/backend.pid)
  ├─ Spawn: uv run python -m uvicorn src.api.server:app
  ├─ Show splash screen while LLMs initialize (~30-180s)
  └─ Load http://127.0.0.1:8000/ (backend serves frontend)
```

## macOS Permissions

On first launch, macOS will prompt for:

| Permission | Why | How to Grant |
|------------|-----|--------------|
| **Screen Recording** | AI vision assistant (screenshot capture) | System Settings > Privacy & Security > Screen Recording > Owlynn |
| **Accessibility** | Read focused UI element text | System Settings > Privacy & Security > Accessibility > Owlynn |
| **Automation** (per-browser) | Read active browser tab URL/title | Prompted automatically when first used |

Permissions persist under the "Owlynn" app identity once the packaged `.app` is used (not dev mode).

## Browser Extension Install

The Owlynn Browser Bridge enables web search via your real browser, page context extraction, and DOM automation.

1. Open Owlynn.app (wait for main UI to load)
2. In Brave: navigate to `brave://extensions`
3. Enable **Developer mode** (toggle in top-right)
4. Click **Load unpacked**
5. Select the extension folder:
   - Packaged app: `/Applications/Owlynn.app/Contents/Resources/browser-extension/`
   - Dev mode: `<repo>/browser-extension/`
6. The extension auto-connects to the backend on `http://127.0.0.1:8000`
7. Verify: click the extension icon — popup should show "Connected"

## Close vs Quit

| Action | What Happens |
|--------|-------------|
| **Click X button** (⌘W) | Window hides to background. Backend + containers keep running. Click dock icon or tray to reopen. |
| **Cmd+Q** | Backend stops (SIGTERM). Containers keep running (data persists). App exits. |
| **Tray > Quit Owlynn** | Same as Cmd+Q. |
| **Tray > Show Owlynn** | Restores hidden window. |

## Building a Release

```bash
cd frontend-v2
npm run build    # tsc -b && vite build && electron-builder
```

### What the Build Does

| Step | Command | Output |
|------|---------|--------|
| 1. TypeScript check | `tsc -b` | Type errors fail the build |
| 2. Vite bundle | `vite build` | `dist/` (frontend SPA), `dist-electron/main.js`, `dist-electron/preload.js` |
| 3. Electron package | `electron-builder` | `dist/Owlynn-0.1.1-arm64.dmg`, `dist/Owlynn-0.1.1-arm64-mac.zip` |

### What Gets Bundled in the .app

```
Owlynn.app/Contents/
  ├─ MacOS/           — Electron binary
  ├─ Resources/
  │   ├─ app.asar     — Vite-bundled frontend + Electron main/preload
  │   ├─ splash.html  — Loading screen (extraResources)
  │   └─ browser-extension/  — Brave extension (extraResources)
  └─ Frameworks/      — Electron frameworks
```

### electron-builder.yml Configuration

Key config in `frontend-v2/electron-builder.yml`:

- **`appId`**: `com.owlynn.app` — unique app identifier
- **`mac.hardenedRuntime`**: `true` — required for notarization
- **`mac.entitlements`**: points to `electron/entitlements.mac.plist` (grants Apple Events)
- **`mac.extendInfo`**: adds `NSAppleEventsUsageDescription` and `NSScreenCaptureUsageDescription` to Info.plist
- **`extraResources`**: bundles `browser-extension/` and `splash.html` into Resources/

Output:
- `frontend-v2/release/Owlynn-0.1.4.dmg` — macOS installer
- `frontend-v2/release/Owlynn-0.1.4-mac-arm64.zip` — portable archive

## Packaging Fixes (v0.1.1)

### Fix 1: `uv` Binary Not Found (spawn uv ENOENT)

**Problem:** Packaged `.app` doesn't inherit the user's shell PATH. `spawn('uv', ...)` fails because `/opt/homebrew/bin/` and `~/.cargo/bin/` aren't in the app's PATH.

**Fix:** Added `findUvPath()` in `electron/main.ts` that checks common install locations:
- `/opt/homebrew/bin/uv` — Homebrew on Apple Silicon
- `/usr/local/bin/uv` — Homebrew on Intel
- `~/.cargo/bin/uv` — cargo install
- `/usr/bin/uv` — system

Falls back to `'uv'` (PATH lookup) for dev mode.

### Fix 2: splash.html Not in Bundle

**Problem:** `vite-plugin-electron` only compiles `main.ts` and `preload.ts`. The `splash.html` file wasn't copied to the `.app` bundle.

**Fix:** Added `electron/splash.html` to `extraResources` in `electron-builder.yml`. The splash window now checks both packaged (`process.resourcesPath`) and dev (`__dirname`) locations.

### Fix 3: YAML Syntax Error in electron-builder.yml

**Problem:** Missing closing quote on `to: "splash.html` line caused YAML parse error during build.

**Fix:** Added closing quote: `to: "splash.html"`.

### Fix 4: Splash Screen Stuck (IPC Event Argument Mismatch)

**Problem:** Splash screen showed all steps stuck on pending — no checkmarks. The `splash-status` IPC listener in `splash.html` used `(_event, data)` callback signature, but the preload's `contextBridge.on()` strips the event argument before passing to the listener. So `_event` received the data object and `data` was `undefined`, causing `updateStep()` to silently fail.

**Fix:** Changed listener from `ipcRenderer.on('splash-status', (_event, data) => ...)` to `ipcRenderer.on('splash-status', (data) => ...)` in `splash.html`.

### Fix 5: Splash Messages Sent Before Window Loaded

**Problem:** `createSplashWindow()` called `loadFile()` which is async, but the Promise was not awaited. The `sendSplash()` calls fired immediately after — before the splash window's renderer had loaded the HTML and registered the IPC listener. Messages were sent into the void.

**Fix:** Changed `createSplashWindow()` to return a `Promise<void>` that resolves on `did-finish-load` event. Startup flow now `await`s the splash load before sending any IPC messages.

### Fix 6: Backend Crash Silent — App Loads But Nothing Works

**Problem:** `spawnBackend()` used fire-and-forget `spawn()`. If the backend process crashed (e.g., missing dependency, import error), the main window still loaded but all API/WS calls failed silently. No error was shown to the user.

**Fix:** 
- `spawnBackend()` now returns a Promise that rejects if the process exits within 2 seconds (crash detection)
- Backend stderr is forwarded to the splash hint area for real-time visibility
- If spawn fails or health check times out, the app stays on the splash screen with the error message instead of transitioning to a broken main window

### Fix 7: Duplicate Containers Conflict

**Problem:** Both `start.sh` and the Electron app tried to start the same containers. If containers were already running, `podman compose up -d` could fail or create conflicts.

**Fix:** `startContainers()` now checks if containers are already running (`podman ps --filter name=owlynn_qdrant --filter name=owlynn_redis`) before trying to start them. Both `start.sh` and the app share the same containers.

### Fix 8: Port Conflict After Backend Kill

**Problem:** `killStaleBackend()` sent SIGKILL but didn't wait for port 8000 to be released. The new backend could fail with "address already in use".

**Fix:** After killing, polls `lsof -ti:8000` up to 10 times (5s total) until the port is free before spawning the new backend.

### Fix 9: Health Check False Positive

**Problem:** `waitForHealth()` passed on the first `agent: "ready"`. If the old backend was still responding (SIGKILL is async), the check could pass on the stale process.

**Fix:** Requires 2 consecutive "ready" responses (2 seconds apart) to confirm the new backend is genuinely healthy.

### Fix 10: Splash Flashes Briefly

**Problem:** When all services were already running, startup completed in ~3 seconds. The splash appeared and disappeared too fast.

**Fix:** Minimum 3-second splash display time. The startup waits until at least 3 seconds have elapsed before transitioning to the main window.

## Version Bump Checklist

1. Edit `frontend-v2/package.json` → `"version": "X.Y.Z"`
2. Run `cd frontend-v2 && npm run build`
3. Test: double-click `.app`, verify splash, verify version in sidebar footer
4. Test: verify permissions persist across app restarts
5. Git commit + tag: `git tag vX.Y.Z && git push --tags`
6. Upload DMG/ZIP to GitHub Releases

## Architecture

```
Owlynn.app (Electron)
  ├─ Splash window (splash.html — loading status)
  ├─ Main window (http://127.0.0.1:8000/ — backend serves frontend)
  ├─ Tray icon (menu bar — Show/Quit)
  ├─ Spawns backend process (uvicorn on :8000)
  └─ Bundles browser-extension/ in Contents/Resources/

Backend connects to:
  ├─ Qdrant (:6333) — container (long-term memory vectors)
  ├─ Redis (:6379) — container (session cache, checkpoints)
  ├─ LM Studio (:1234) — native app (local LLM inference)
  ├─ Brave Browser (via extension WebSocket) — native app
  └─ DeepSeek API (cloud, opt-in) — internet
```

## Data Persistence

| Data | Location | Persists Across App Updates? |
|------|----------|------------------------------|
| Qdrant vectors | Docker volume `qdrant_data` | ✅ Yes |
| Redis checkpoints | Docker volume `redis_data` | ✅ Yes |
| User profile | `data/user_profile.json` | ✅ Yes (atomic writes) |
| Memories | `data/memories.json` | ✅ Yes (atomic writes) |
| API keys | `~/.owlynn/secrets.env` | ✅ Yes (atomic writes) |
| Traces | `~/.owlynn/traces/` | ✅ Yes |
| Config | `~/.owlynn/config.json` | ✅ Yes |
| PostgreSQL (optional) | Docker volume `postgres_data` | ✅ Yes |

Container data persists in Docker/Podman named volumes. Running `podman compose up -d` does not affect existing volumes.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "spawn uv ENOENT" | Fixed in v0.1.1. If still occurs, ensure uv is installed at `/opt/homebrew/bin/uv` or `~/.cargo/bin/uv` |
| "LM Studio not responding" | Open LM Studio, load a model, click "Start Server" |
| "Backend startup timed out" | Check LM Studio is running. Check `~/.owlynn/logs/` for errors |
| "Port 8000 in use" | Kill stale process: `lsof -ti:8000 \| xargs kill -9` |
| "Containers not starting" | Check podman/docker is running: `podman ps` |
| "Brave Browser not found" | Install Brave Browser from [brave.com](https://brave.com) |
| "Extension not connected" | Sideload extension (see Browser Extension Install above) |
| Permission prompts re-appearing | Use the packaged `.app` (not dev mode) so macOS persists permissions |
| Blank window after update | Clear Electron cache: `rm -rf ~/Library/Application Support/owlynn/` |
| Splash stuck on "Initializing AI" | Check LM Studio model is loaded. Backend logs in `~/.owlynn/logs/` |

## Related

- [`docs/guides/dev-startup.md`](dev-startup.md) — development startup guide
- [`docs/features/BROWSER_EXTENSION.md`](../features/BROWSER_EXTENSION.md) — browser extension features
- [`docs/architecture/CLOUD-LLM-ARCHITECTURE.md`](../architecture/CLOUD-LLM-ARCHITECTURE.md) — cloud LLM integration
- [`docs/HITL.md`](../HITL.md) — human-in-the-loop execution policy
