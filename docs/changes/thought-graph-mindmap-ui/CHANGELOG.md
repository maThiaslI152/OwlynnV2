# Changelog — Thought Graph & Mindmap Canvas Architecture

**Date:** 2026-08-23  
**Status:** Completed & Verified  

---

## 1. Overview

Replaced the legacy sidebar-driven chat layout with a unified **Thought Graph & Mindmap Canvas Architecture**. Chat sessions are now represented as interconnected nodes on an interactive canvas that Owlynn and the user can traverse, branch, and organize seamlessly across Normal, Study, and Pentest modes.

---

## 2. Key Changes

### A. Dual Canvas Visual Renderers
- **Normal & Study Modes — Coggle-Style Organic Mindmap:**
  - Implemented organic canvas renderer (`drawCoggleNode` in `MindmapCanvas.tsx`) featuring glowing rounded pill badges, pastel branch colors (Lime, Cyan, Yellow, Coral, Pink, Lavender), and smooth bezier curves connecting conversational branches.
- **Pentest Mode — Autodesk Maya / Blueprint Node Editor:**
  - Implemented CAD blueprint node editor renderer (`drawMayaNode` in `MindmapCanvas.tsx`) with dark CAD grid background (`drawBackground`), rectangular module blocks with category headers (`TARGET / SCOPE`, `RECON / ENUM`, `VULNERABILITY`, `EXPLOIT / ACCESS`), green input pins (`in`) and orange output pins (`out`), and animated directional data particle wires.

### B. Layout & Navigation Overhaul
- **Sidebar Removal:** Completely eliminated the legacy left sidebar (Workspace / Chats / Knowledge) to give 100% of the screen width to the Thought Graph and Conversation workspace.
- **Top Header Mode Switcher:** Moved mode switcher pills (`[ ✨ Normal ] [ 🎓 Study ] [ 🛡️ Pentest ]`) directly into the center of `MacMenuBar.tsx`.
- **Status Bar Enhancements:**
  - Added real-time Brave / Chrome Extension status pill (`🌐 Brave Ext ●`) connected to `/api/browser_extension/status`.
  - Added System Health Popover (`⚡ System ^`) displaying live status of LM Studio, Podman containers, Redis, Qdrant, and active models without navigating away from the canvas.
- **Layout Switcher:** Added interactive view mode toggle: `Chat`, `Split Graph` (48% canvas / 52% chat), and full-screen `Mindmap` (100% canvas).

### C. Backend Thought Graph Engine
- **Persistence & Relations:** Created `src/memory/thought_graph.py` with `ThoughtNode` and `ThoughtEdge` SQLAlchemy models, supporting automated chat conversation seeding, custom tags, coordinates, and relation weights.
- **REST Endpoints:** Added `/api/graph/data`, `/api/graph/nodes`, and `/api/graph/edges` endpoints in `src/api/routes/thought_graph.py`.
- **System Info Endpoint:** Added `/api/system-info` in `src/api/server.py` for live container, Redis, Qdrant, and model diagnostics.

---

## 3. Files Modified & Created

| File | Change |
| :--- | :--- |
| `src/memory/thought_graph.py` | [NEW] SQLAlchemy models and manager for thought nodes and edges |
| `src/api/routes/thought_graph.py` | [NEW] REST API router for thought graph CRUD and layout queries |
| `src/api/server.py` | Mounted `/api/graph` routes and added `/api/system-info` health check |
| `frontend-v2/src/components/mindmap/MindmapCanvas.tsx` | [NEW] Full 2D HTML5 ForceGraph canvas with Coggle & Maya renderers |
| `frontend-v2/src/components/layout/AppShell.tsx` | Removed left sidebar, integrated split/full mindmap layout switcher |
| `frontend-v2/src/components/layout/MacMenuBar.tsx` | Integrated mode switcher pills in top menu bar center |
| `frontend-v2/src/components/layout/StatusBar.tsx` | Added Brave extension status pill and system health popover |
| `frontend-v2/src/index.css` | Updated `.app-shell` and `.center-panel` to full-width flexbox |
| `tests/test_thought_graph.py` | [NEW] Backend unit and property tests for thought graph engine |

---

## 4. Verification & Quality Assurance

- **Visual Validation:** Verified via headless Brave Browser / Chromium screenshots across all modes.
- **TypeScript:** `npx tsc --noEmit` -> **0 errors (100% clean)**.
- **Frontend Tests:** `npm run test -- --run` -> **130 / 130 passing across 19 test files (100%)**.
- **Backend Tests:** `pytest tests/test_thought_graph.py` -> **3 / 3 passing (100%)**.
