---
status: active
category: changelog
last_updated: 2026-07-07
owner: ai-agent
audience: human
---

# Study Mode Revamp — 2026-07-07

## Summary

We have fully developed the placeholder Study Mode dashboard into a highly functional and polished student hub. It interfaces directly with the backend `/api/study/dashboard` endpoint to display global study streaks, exam countdowns, course tasks, and flashcard review queues. We have also enforced strict workspace mode isolation across the application.

## Changes

### Modified Files

| File | Changes |
|------|---------|
| `frontend-v2/package.json` | Bumped version to `0.1.5` |
| `frontend-v2/src/components/StudyDashboard.tsx` | Full rewrite: Integrated API dashboard data, built streak/exam countdown hero widget, created tasks/flashcard sidebar widgets, wired `DeckBrowserModal` to review due decks. |
| `frontend-v2/src/components/SubjectCard.tsx` | Added progress metrics (mastery, streak, due cards count, last studied timestamp) and customized theme/border glows for subjects with due cards. |
| `frontend-v2/src/components/AppShell.tsx` | Implemented sidebar workspace project filtering based on active app mode (`study` / `pentest` / `normal`). |
| `frontend-v2/src/App.tsx` | Passed `activeMode` down during workspace project creation so the workspace inherits the correct mode classification. |
| `src/memory/project.py` | Added `mode` parameter to `create_project()` database utility. |
| `src/api/routes/project.py` | Updated `/api/projects` POST endpoint to parse `mode` from body and pass it to project manager. |
| `frontend-v2/src/index.css` | Added utility `.hover-brighten` class. |

## Highlights

### 1. Unified Flashcard Integration
Users can now browse and study flashcard decks directly from the Study Dashboard. Decks requiring review are highlighted with an amber glowing shadow and a "Due" badge. Clicking a deck opens the `DeckBrowserModal` for study sessions.

### 2. Strict Workspace Isolation
To prevent distraction and organize context, normal coding workspaces and pentest scenario workspaces are completely hidden when in Study Mode. Conversely, when in Normal Mode, course notebooks are filtered out of the sidebar dropdown. Workspaces created while in a specific mode automatically inherit that mode classification.
