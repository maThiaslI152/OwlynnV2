# Self-Contained MVP Packaging (v0.3.0)

## Summary

Owlynn v0.3.0 is a double-click personal Mac app: the Python backend, Alembic migrations, Chart.js vendor bundle, and MVP Docker compose file are bundled inside the `.app`. Only **Podman/Docker Desktop** and **LM Studio** remain external dependencies.

## Changes

### Phase 1 (startup parity — prior session)
- Added `docker-compose.mvp.yml` (Postgres pgvector + StirlingPDF only)
- Electron startup: MVP containers, `DATABASE_URL`, Alembic migrations, `config.json`, `OWLYNN_PACKAGED=1`
- Aligned `setup.sh` / `start.sh` with MVP compose

### Phase 2 — Backend bundle
- **`scripts/build_backend_bundle.sh`**: `uv sync` → arm64 `.venv`, vendors Chart.js, copies payload to `dist/backend-bundle/`
- **`frontend-v2/electron-builder.yml`**: `extraResources` includes `owlynn-backend`
- **`frontend-v2/package.json`**: build script runs backend bundle before electron-builder
- **`frontend-v2/electron/main.ts`**: first-launch extraction to `~/.owlynn/runtime/`, version-aware refresh, bundled `.venv` Python spawn

### Phase 3 — UX + docs
- Splash blocks with clear message when Podman/Docker missing (packaged mode)
- One-time Brave extension hint toast on first packaged launch
- Version bump to **0.3.0**
- Rewrote `docs/guides/app-release.md` for 2 external deps
- Updated `AGENTS.md` task routing row

### Docling models (deferred)
- ~2 GB Docling download remains optional in dev (`setup.sh` step 3)
- Packaged app does **not** bundle Docling weights; lazy on-demand download on first document upload is planned for a follow-up (StirlingPDF handles most PDF intake)

## User data layout

```
~/.owlynn/
  config.json              # { project_root, runtime_version, written_at }
  runtime/                 # extracted backend (refreshed on app update)
  workspace/               # project files, HTML charts
  secrets.env              # optional DeepSeek key
  logs/crash.log
  backend.pid
  .extension_hint_shown    # first-launch Brave extension toast flag
```

## Build

```bash
cd frontend-v2 && npm run build
# Output: dist/Owlynn-0.3.0-arm64.dmg
```

Built on macOS 14+ (Apple Silicon). Bundled `.venv` is platform-specific — rebuild the DMG on the target machine architecture.

## Files touched

- `scripts/build_backend_bundle.sh` (new)
- `frontend-v2/electron-builder.yml`
- `frontend-v2/package.json`
- `frontend-v2/electron/main.ts`
- `frontend-v2/electron/splash.html`
- `frontend-v2/src/App.tsx`
- `frontend-v2/src/test-setup.ts`
- `pyproject.toml`
- `docs/guides/app-release.md`
- `AGENTS.md`
