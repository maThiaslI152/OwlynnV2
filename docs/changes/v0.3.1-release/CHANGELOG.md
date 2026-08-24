---
status: active
category: changelog
audience: agent
last_updated: 2026-08-24
owner: ai-agent
---

# Changelog: Owlynn v0.3.1

> **Purpose:** Desktop DMG release notes for tool-bind TTFT cuts and mindmap/chat reliability.

## 2026-08-24 — v0.3.1 desktop package

### What

- **Local tool bind cap:** live-data / informational turns bind the `web_search` toolbox (≈5 tools) instead of the 36-tool `"all"` catalog. Lean `"all"` drops screen-assist and ipynb (still on named toolboxes). Context chip counts **Schemas** on the post-rerank list.
- **Mindmap / chat UX:** WebSocket waits for the local-run token before connect; composer send sits in the input pill; branches auto-hide on graph and dock in Chat; canvas ResizeObserver matches host size; action bar wraps in Split Graph.
- **Version:** `0.3.1` in `frontend-v2/package.json`, `pyproject.toml`, `__APP_VERSION__`. Artifacts: `frontend-v2/dist/Owlynn-0.3.1-arm64.dmg` (~649 MB), `.zip`, and `mac-arm64/Owlynn.app`.

### Why

Packaging the bind-cap and canvas fixes so a double-click `.app` matches the live stack: faster first-token on “latest version” questions, and a mindmap that is clickable and not clipped.

### Files

- Routing / tools: `src/agent/routing/router.py`, `deterministic.py`, `src/agent/tool_sets.py`, `src/agent/core/complex.py`, `complex_utils/context_breakdown.py`
- UI: `frontend-v2/src/App.tsx`, `Composer.tsx`, `MindmapCanvas.tsx`, `AppShell.tsx`, `index.css`, `CloudUsageChip.tsx`
- Release: `docs/guides/app-release.md`, this changelog

### Related

- [`docs/changes/local-tool-bind-cap/CHANGELOG.md`](../local-tool-bind-cap/CHANGELOG.md)
- [`docs/guides/app-release.md`](../../guides/app-release.md)
