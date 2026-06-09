---
status: active
category: guide
last_updated: 2026-06-09
owner: ai-agent
---

# Phase 3: Screen Assist

Native macOS context capture for pentest and terminal workflows. Python orchestration layer — independent of the Electron preview UI.

## Architecture decisions

1. **Headless Python on macOS** — AX, AppleScript, tmux subprocesses; not bound to Electron.
2. **Local tmux on Mac** — `tmux capture-pane -p` from the presentation terminal (zero overhead on Kali VM).
3. **Kali via SSH** — remote tmux on the VM; no agent dependencies inside Kali.
4. **AX blindspot** — when Accessibility returns no text, crop 512×512 and run Phase 2 `transcribe_crop()`.

## Flow

```text
Router (pentest / terminal keywords)
  → toolbox: screen_assist
  → complex_llm binds capture_* tools
  → MacScreenAssistGateway
       ├─ tmux.py          local pane
       ├─ ax_macos.py      AX + vision crop
       ├─ browser.py       AppleScript + optional CDP
       └─ kali_ssh.py      ssh user@host tmux capture-pane
```

## Modules

| Path | Role |
|------|------|
| `src/tools/screen_assist/gateway.py` | `MacScreenAssistGateway` |
| `src/tools/screen_assist/tools.py` | LangChain `@tool` wrappers |
| `src/tools/screen_assist/tmux.py` | Local tmux capture |
| `src/tools/screen_assist/ax_macos.py` | AX + screencapture crop |
| `src/tools/screen_assist/browser.py` | Tab URL + Playwright CDP |
| `src/tools/screen_assist/kali_ssh.py` | SSH remote tmux |

## Tool reference

### `capture_local_terminal(session="")`

Runs `tmux capture-pane -p -t <session>`. Default session from `screen_assist.tmux_session` (`owlynn`).

### `read_screen_element(x, y)`

Returns front app, window, focused AX value. Empty AX → `screencapture -R` crop → vision JSON block.

### `get_active_browser_context()`

AppleScript: Chrome → Safari → Arc. If `browser_cdp_url` set, appends Playwright `innerText` snapshot.

### `capture_kali_terminal(session="")`

`ssh -o BatchMode=yes user@host 'tmux capture-pane -p -t session'`. Requires `screen_assist.kali.host`.

## Configuration

```yaml
screen_assist:
  enabled: true
  tmux_session: owlynn
  tmux_history_lines: 200
  ax_blindspot_crop_size: 512
  browser_cdp_url: ""
  kali:
    host: ""
    user: kali
    port: 22
    tmux_session: main
    identity_file: ""
```

Environment overrides: `KALI_SSH_HOST`, `KALI_SSH_USER`, `KALI_SSH_PORT`, `SCREEN_ASSIST_TMUX_SESSION`.

## Permissions (macOS)

- **Accessibility** — System Settings → Privacy → Accessibility → Terminal/Python/Owlynn
- **Screen Recording** — required for `screencapture` crop fallback
- **SSH keys** — `BatchMode=yes`; configure `identity_file` or ssh-agent for Kali

## Router integration

- Toolbox category `screen_assist` in `TOOLBOX_REGISTRY`
- Auto-appended when `scenario_id == pentest` or terminal/screen keywords match
- Tools are **SAFE_TOOLS** (read-only, no HITL approval)

## Tests

```bash
PYTHONPATH=$(pwd) python -m pytest -q tests/test_phase3_screen_assist.py -m "not network"
```

## Related

- [memory-vision-screen-roadmap.md](./memory-vision-screen-roadmap.md)
- [VISION_PROXY.md](../architecture/VISION_PROXY.md)
