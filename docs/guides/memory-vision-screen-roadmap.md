---
status: active
category: guide
last_updated: 2026-06-09
owner: ai-agent
---

# Memory · Vision · Screen Assist Roadmap

Three-phase upgrade for Owlynn pentest/research workflows: fast memory routing, cloud-safe vision, and native macOS screen context.

## Overview

| Phase | Goal | Status |
|-------|------|--------|
| **1** | Memory orchestration (L0–L3, gated retrieval, async extraction) | ✅ Shipped |
| **2** | Vision proxy (JSON OCR → DeepSeek text path) | ✅ Shipped |
| **3** | Screen assist (tmux, AX, browser, Kali SSH) | ✅ Shipped |

```text
User message
  → memory_inject_lite → router → memory_retrieve → complex path
  → [images] vision_proxy → cloud
  → [pentest / terminal] screen_assist tools → local context
  → memory_write → PII scrub → extraction worker
```

## Phase 1 — Memory orchestration

**Doc:** [memory-orchestration-phase1.md](./memory-orchestration-phase1.md)

- Split inject: lite before router, vector search gated after
- Custom 8B extraction (no `mem0 infer=True`), PII scrub before LTM
- Pentest + research L2/L3 markdown under `scenarios/`
- Redis extraction worker, cloud brief compression

## Phase 2 — Vision proxy

**Doc:** [../architecture/VISION_PROXY.md](../architecture/VISION_PROXY.md)

- Local VLM returns structured JSON (`text_blocks`, `ui_elements`, `subjects`)
- Lazy-loaded client with idle unload
- `transcribe_crop()` for coordinate blindspots (used by Phase 3)
- Cloud path strips `image_url`; failure → `complex-default` multimodal

## Phase 3 — Screen assist

**Doc:** [screen-assist-phase3.md](./screen-assist-phase3.md)

- Headless **Python on macOS** (not Electron-only)
- **Local tmux** `capture-pane` on Mac terminal (iTerm2/Terminal)
- **Accessibility API** via AppleScript; 512×512 vision crop when AX empty
- **Browser** URL/title (Chrome, Safari, Arc); optional Playwright CDP DOM
- **Kali** remote tmux over SSH (VM separate from Mac presentation layer)

### Tools (read-only, HITL-safe)

| Tool | Purpose |
|------|---------|
| `capture_local_terminal` | Local tmux pane text |
| `read_screen_element` | AX context at (x, y) + vision fallback |
| `get_active_browser_context` | Front tab + optional DOM |
| `capture_kali_terminal` | SSH → remote tmux pane |

Router adds `screen_assist` toolbox for pentest `scenario_id` or terminal/screen keywords.

## Configuration

```yaml
screen_assist:
  enabled: true
  tmux_session: owlynn
  ax_blindspot_crop_size: 512
  browser_cdp_url: ""
  kali:
    host: ""          # or KALI_SSH_HOST env
    user: kali
    tmux_session: main
```

## Tests

```bash
PYTHONPATH=$(pwd) python -m pytest -q \
  tests/test_phase1_memory_orchestration.py \
  tests/test_vision_schema.py tests/test_vision_proxy.py \
  tests/test_phase3_screen_assist.py -m "not network"
```

## Related

- [MEMORY.md](../MEMORY.md)
- [DEEPSEEK_V4_INTEGRATION.md](../architecture/DEEPSEEK_V4_INTEGRATION.md)
- Frontend capture UI: `frontend-v2/src/components/ScreenAssistPanel.tsx` (Electron `screencapture`; backend tools are separate)
