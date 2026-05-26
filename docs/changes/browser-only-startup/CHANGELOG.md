# CHANGELOG: browser-only-startup

> **Change:** Overhaul startup process to be exclusively browser-based.
> **Created:** 2026-06-01T19:16:00Z

## Tasks

| # | Task | Status | Date |
|---|------|--------|------|
| 1 | Update run-user-test.mdc for browser-only launch | done | 2026-06-01 |
| 2 | Update dev-startup.md — mark Tauri as paused | done | 2026-06-01 |
| 3 | Polish start.sh — consistency fixes | done | 2026-06-01 |
| 4 | Verify backend startup reliability | done | 2026-06-01 |
| 5 | End-to-end browser-only startup verification | done | 2026-06-01 |

### Task 1: Update run-user-test.mdc

- Replaced Tauri `tauri dev` launch with Vite dev server (`npx vite --host 127.0.0.1 --port 5173`)
- Added `block_until_ms: 0` pattern for persistent backend startup (replaces `&` which causes premature exit)
- Added Tauri paused notice at top and in troubleshooting
- Removed Tauri-specific troubleshooting (CLI path, folder errors, TCC permissions)
- Removed `npm run build` requirement (Vite dev server serves source directly with HMR)

### Task 2: Update dev-startup.md

- Added "Tauri Desktop App (Paused)" section with clear status and resumption instructions
- Updated Step 5: changed "React 19 + Vite + Tauri app" to "React 19 + Vite app", marked browser-only as current mode
- Architecture diagram already browser-only — no changes needed

### Task 3: Polish start.sh

- Updated shebang comment: "browser-first" → "browser-only, no Tauri (paused)"
- Bash syntax check passes
- No functional changes — script already works for browser-only

### Task 4: Verify backend startup reliability

- Backend started with `block_until_ms: 0` — persisted >30s (previously exited in ~5s with `&`)
- Health check returns `{"status":"ok","agent":"ready"}`
- Process listening on `localhost:8000` confirmed via `lsof`

### Task 5: End-to-end verification

- Vite dev server started on port 5173 via `block_until_ms: 0`
- API proxy verified: `curl 5173/api/health` → `{"status":"ok","agent":"ready"}`
- No Tauri processes running (`pgrep -f tauri` → none)
- Vite listening on `localhost:5173` confirmed via `lsof`

### Task 1: Update run-user-test.mdc

- Replaced Tauri `tauri dev` launch with Vite dev server (`npx vite --host 127.0.0.1 --port 5173`)
- Added `block_until_ms: 0` pattern for persistent backend startup (replaces `&` which causes premature exit)
- Added Tauri paused notice at top and in troubleshooting
- Removed Tauri-specific troubleshooting (CLI path, folder errors, TCC permissions)
- Removed `npm run build` requirement (Vite dev server serves source directly with HMR)
