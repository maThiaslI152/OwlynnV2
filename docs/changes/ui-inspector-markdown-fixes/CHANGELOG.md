---
status: active
category: changelog
audience: agent
last_updated: 2026-06-10
owner: ai-agent
---

# Changelog: Inspector Popover & Markdown Table Responsiveness

> **Purpose:** UI fixes for the cloud usage chip popover (transparent overlap) and markdown tables overflowing narrow chat panels.

## BUG-15 — Cloud usage popover transparent overlap

**Symptom:** Clicking the `$0.010` chip opened a popover where text overlapped the **Cloud & Usage** inspector section below — background was semi-transparent (`--bg-elevated` at ~42% opacity).

**Fix:**

- `.cloud-usage-popover` — opaque `rgba(8, 16, 30, 0.97)` + `backdrop-filter`, higher `z-index`
- `.inspector-header` — `position: relative`, `z-index: 30`, `overflow: visible`
- `body.tauri-glass .cloud-usage-popover` — extra opacity override for glass theme

**Files:** `frontend-v2/src/index.css`

## BUG-16 — Markdown tables not responsive in narrow panels

**Symptom:** When the center panel or message bubble is narrow, GFM tables (e.g. game comparison tables) overflow and clip the rightmost columns with no scroll or wrap.

**Fix:**

- Wrap `<table>` in `<div className="msg-table-wrap">` (`AppShell.tsx` `MessageContent`)
- `min-width: 0` on `.message`, `.message-body`, `.message-bubble` (flex shrink)
- `.msg-table-wrap` — `overflow-x: auto`
- `.msg-table` — `table-layout: fixed`, `overflow-wrap: anywhere` on cells

**Files:** `frontend-v2/src/components/AppShell.tsx`, `frontend-v2/src/index.css`

## Inspector Cloud & Usage verification

- `data-testid="inspector-cloud-usage-section"` / `-body` on `CollapsibleSection`
- `CloudUsagePanel` test: session cost, daily budget, call count, last-call log

**Files:** `frontend-v2/src/components/AppShell.tsx`, `frontend-v2/src/components/__tests__/cloud-settings.test.tsx`

## Related

- [`docs/BUG-TRACKER.md`](../../BUG-TRACKER.md) — BUG-15, BUG-16
- [`docs/changes/cloud-usage-context-chip/CHANGELOG.md`](../cloud-usage-context-chip/CHANGELOG.md) — chip + context breakdown
