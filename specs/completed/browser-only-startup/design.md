# Design: Browser-Only Startup

> **Purpose:** Define how the browser-only startup requirements will be implemented. Tauri is paused — mark it as such, keep code intact, but update all active startup paths to browser-only.

## Architecture Overview

The change is documentation- and script-focused. Three artifacts are modified: the `run-user-test` agent skill (from Tauri → browser), the `dev-startup.md` guide (add paused notice), and `start.sh` (minor reliability polish). No product code changes. Backend startup reliability is addressed by using `block_until_ms: 0` (persistent background) instead of `&` (ephemeral background) when agents start the backend.

## System Diagram

```mermaid
flowchart TD
  A[User: "launch Owlynn"] --> B[Agent reads run-user-test.mdc]
  B --> C{Check ports}
  C -->|containers down| D[podman compose up -d]
  C -->|8000 down| E[start backend: block_until_ms=0]
  C -->|5173 down| F[start frontend: npx vite]
  D --> E
  E --> F
  F --> G[Browser: http://127.0.0.1:5173]
```

## Component / Module Breakdown

| Component | Responsibility | Files |
|-----------|---------------|-------|
| Agent skill | Tells Cursor agents how to launch Owlynn for user testing | `.cursor/rules/run-user-test.mdc` |
| Dev startup guide | Authoritative dev startup reference | `docs/guides/dev-startup.md` |
| Launcher script | One-command startup for developers | `start.sh` |

## Changes Per File

### 1. `.cursor/rules/run-user-test.mdc`

**Current behavior:** Skill instructs agents to build frontend-v2, then launch `tauri dev`. Backend started with `&` (fragile).

**New behavior:** Skill instructs agents to:
1. Start containers if down
2. Start backend with `block_until_ms: 0` (persistent background — no premature exit)
3. Start Vite dev server with `block_until_ms: 0`
4. Verify all ports respond
5. Note: "Tauri desktop app is paused. Use browser at http://127.0.0.1:5173"

**Key diff:**
```
- Launch Tauri desktop app from project root
- Build frontend-v2 to pick up latest changes
+ Start frontend Vite dev server (browser-only)
+ Verify frontend at http://127.0.0.1:5173
+ Note: Tauri desktop app development is paused
```

### 2. `docs/guides/dev-startup.md`

**Current behavior:** References Tauri in Step 5 (Frontend), architecture diagram mentions Tauri, no pause notice.

**New behavior:**
- Tauri section explicitly marked **"Paused"** with notice: "Tauri desktop app development is paused as of 2026-06. Browser-only development at http://127.0.0.1:5173 is the current mode."
- Architecture diagram simplified to browser-only path
- Tauri-related troubleshooting entries kept but marked "(paused)"

### 3. `start.sh`

**Current behavior:** Already says "browser-first, no Tauri" in header. Works correctly for manual terminal use.

**Changes:** None required for functionality. Minor polish: clarify the shebang comment to "browser-only, no Tauri" for consistency.

### 4. Backend Startup Reliability

**Root cause:** When agents use `Shell` with `&` at end of command, the background process is tied to the shell session. When the Shell tool's session ends, the background process gets killed.

**Fix:** Agents must use `block_until_ms: 0` instead of `&`. This tells the Shell tool to run the command as a persistent background process that outlives the tool call. The `run-user-test.mdc` skill will specify this pattern.

## Error Handling Strategy

- Agent startup: if any service fails to start, report the specific port and suggest fix
- `start.sh`: existing error handling is adequate — containers, LM Studio, stale port cleanup all handled
- Backend crash: agent must check `lsof -iTCP:8000` after startup; if not listening, read the terminal output file for errors

## Trade-offs and Decisions

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| Keep Tauri code, mark paused | Easy to resume later; no risk of breaking existing config | Remove Tauri entirely — cleaner but harder to undo |
| Use `block_until_ms: 0` for backend | Shell tool's documented pattern for persistent processes | `nohup` / `disown` — doesn't work in Shell tool context |
| Start Vite directly, not via `tauri dev` | `tauri dev` compiles Rust and opens a desktop window — unnecessary overhead | Keep `tauri dev` but suppress window — defeats purpose of browser-only |
| Modify existing `run-user-test.mdc`, no new skill | Single source of truth for agent launch behavior | Create a separate `browser-launch` skill — adds fragmentation |

## Open Questions

- [x] ~~Should Tauri config/code be removed or just documented as paused?~~ → Marked as paused (per user decision)
- [x] ~~Is the backend startup issue in scope?~~ → Yes, fix via `block_until_ms: 0` pattern in skill
- [x] ~~Should we add a `--backend-only` flag to `start.sh`?~~ → Out of scope for this change

## References

- `requirements.md` — AC-1 through AC-5
- `plan_ref: .cursorplan/active/browser-only-startup/plan.md`
- `.cursor/rules/run-user-test.mdc` — current agent launch skill
- `docs/guides/dev-startup.md` — current dev startup guide
- `start.sh` — current launcher script

## Approval

- `design-review` AskQuestion: approved (2026-06-01T19:20:00Z)
