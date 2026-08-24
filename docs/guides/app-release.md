---
status: active
category: guide
last_updated: 2026-08-24
owner: ai-agent
audience: human
---

# Owlynn App Release Guide (v0.3.1)

> **Purpose:** Build, distribute, install, and troubleshoot the self-contained Owlynn Electron app.

## External dependencies (user machine)

| Dependency | Required? | Role |
|------------|-----------|------|
| **macOS 14+ (Apple Silicon)** | Yes | Electron 42, bundled arm64 Python |
| **Podman Desktop or Docker Desktop** | Yes | Auto-starts Postgres (pgvector) + StirlingPDF on launch |
| **LM Studio** | Yes | Local LLM + embedding inference on `:1234` |
| git clone / uv / system Python | **No** | Backend bundled inside `.app` |
| Brave Browser | Recommended | Web search via bundled extension |

## End-user install (no git clone)

1. **Install Podman Desktop** — [podman-desktop.io](https://podman-desktop.io) (or Docker Desktop)
2. **Install LM Studio** — [lmstudio.ai](https://lmstudio.ai), load `gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m`, start local server on `:1234`
3. **Install Owlynn** — drag `Owlynn-0.3.1-arm64.dmg` to `/Applications`
4. **First launch** — right-click → Open (unsigned app Gatekeeper bypass)
5. **Optional:** load Brave extension from `Owlynn.app/Contents/Resources/browser-extension/` (toast on first launch)

## What happens on launch

```
Owlynn.app double-clicked
  │
  ├─ Extract backend bundle → ~/.owlynn/runtime/ (first launch or version bump)
  ├─ Write ~/.owlynn/config.json
  ├─ Start containers: postgres + stirling-pdf (docker-compose.mvp.yml)
  ├─ alembic upgrade head
  ├─ Wait for LM Studio :1234 (120s, then continue degraded)
  ├─ Spawn ~/.owlynn/runtime/.venv/bin/python -m uvicorn ...
  └─ Load http://127.0.0.1:8000/
```

## Building a release (developer)

**Prerequisites on builder Mac:** Node 18+, uv, Podman/Docker (for local smoke test only).

```bash
cd frontend-v2
npm run build
```

### Build pipeline

| Step | Command | Output |
|------|---------|--------|
| 1. Backend bundle | `bash ../scripts/build_backend_bundle.sh` | `dist/backend-bundle/` (src, alembic, .venv, compose) |
| 2. TypeScript | `tsc -b` | type-check electron + frontend |
| 3. Vite bundle | `vite build` | `dist/`, `dist-electron/` |
| 4. Electron package | `electron-builder` | `dist/Owlynn-0.3.1-arm64.dmg` |

### What gets bundled

```
Owlynn.app/Contents/Resources/
  ├─ app.asar                    — Vite frontend + Electron main/preload
  ├─ owlynn-backend/             — Python backend + .venv + alembic + compose
  ├─ browser-extension/          — Brave extension
  └─ splash.html                 — Startup splash
```

User-writable runtime extracted to `~/.owlynn/runtime/` on first launch (preserves `secrets.env`, `workspace/` across updates).

## Browser extension install

1. Open Owlynn, wait for main UI
2. Brave → `brave://extensions` → Developer mode → **Load unpacked**
3. Select `/Applications/Owlynn.app/Contents/Resources/browser-extension/`
4. Verify popup shows "Connected"

## Close vs quit

| Action | Result |
|--------|--------|
| Click X (⌘W) | Window hides; backend + containers keep running |
| Cmd+Q / Tray → Quit | Backend stops; containers stopped via compose |

## Version bump checklist

1. `frontend-v2/package.json` → `"version": "X.Y.Z"`
2. `pyproject.toml` → matching version
3. `frontend-v2/src/test-setup.ts` → `__APP_VERSION__`
4. `cd frontend-v2 && npm run build`
5. Test packaged `.app`: splash, chat, mindmap, offline chart
6. Tag: `git tag vX.Y.Z && git push --tags`

## Data persistence

| Data | Location | Survives app update? |
|------|----------|---------------------|
| Postgres vectors | Docker volume `postgres_data` | Yes |
| Thought Graph | Postgres | Yes |
| Workspace files | `~/.owlynn/workspace/` | Yes |
| API keys | `~/.owlynn/secrets.env` | Yes |
| Runtime code | `~/.owlynn/runtime/` | Refreshed on version bump |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Podman or Docker required" on splash | Install Podman Desktop or Docker Desktop, relaunch |
| "LM Studio offline" | Open LM Studio, load model, start server |
| "Bundled Python not found" | Reinstall from fresh DMG; check `~/.owlynn/runtime/.venv/` |
| Backend startup timeout | Check `~/.owlynn/logs/crash.log` |
| Extension not connected | Load unpacked from Resources (see above) |
| Gatekeeper blocks app | Right-click → Open on first launch |

## Related

- [`docs/guides/dev-startup.md`](dev-startup.md) — development from git checkout
- [`docs/changes/v0.3.1-release/CHANGELOG.md`](../changes/v0.3.1-release/CHANGELOG.md) — v0.3.1 changelog
- [`docs/changes/self-contained-mvp/CHANGELOG.md`](../changes/self-contained-mvp/CHANGELOG.md) — v0.3.0 self-contained MVP
