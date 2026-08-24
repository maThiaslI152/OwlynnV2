# Changelog — Organic Map Scaling

**Date:** 2026-08-24  
**Status:** Complete (backend + canvas + branch list)

---

## 1. Overview

Thought Graph API returns cluster and dormancy metadata; the Mindmap Canvas fades dormant threads, optionally drifts unplaced nodes outward, groups related chats visually, and completes thread lifecycle (New Thread / New Branch / Delete) without merging LangGraph identities.

## 2. What

### Backend
- Durable `topic_cluster_id`, `topic_label`, `dormancy_score`, `importance_score` on `thought_nodes`
- Derived payload: `is_dormant`, `fade_alpha`, `radial_tier`, `allow_radial_drift`, `radial_multiplier`, `visual_mode`
- Composite ranking; `show_dormant`, `search`, `focus_node_id`, `max_nodes`; edge prune + top-K
- Immediate revive on `get_or_create` / node GET / non-canvas updates

### Frontend
- `fade_alpha` / `visual_mode` on nodes and links; dormant links drop particle intensity
- Radial dormancy force only when `allow_radial_drift` and coords unset; light cluster cohesion
- Select dormant → `GET /api/graph/nodes/{id}` revive, brighten, focus; graph loads pass `focus_node_id` / `search=`
- Branches list grouped by cluster, dormant de-emphasized; search overrides fade
- **Focus recent** toggles `show_dormant=false`; New Thread / New Branch / Delete on canvas

## 3. Why

The 300-node recency dump did not scale: old topics competed with active ones, and semantic grouping was only implicit in edges.

## 4. Files

| File | Change |
|------|--------|
| `src/memory/db_models.py` | New ThoughtNode columns |
| `src/memory/thought_graph.py` | Scoring, clustering, prune, revive, backfill |
| `src/api/routes/thought_graph.py` | Graph query params |
| `alembic/versions/c3d4e5f6a7b8_thought_node_cluster_dormancy.py` | Migration |
| `tests/test_thought_graph.py` | Cluster / dormancy / prune / revive / search tests |
| `tests/test_organic_map_backend.py` | Chat-only identity + workspace-tool exclusion |
| `frontend-v2/src/components/mindmap/organicMap.ts` | Fade, grouping, force helpers |
| `frontend-v2/src/components/mindmap/MindmapCanvas.tsx` | Decay render, revive, search, Focus recent, branch groups, New Thread/Delete |
| `frontend-v2/src/components/mindmap/MindmapCanvas.test.tsx` | Frontend regression coverage |
| `docs/features/MEMORY.md`, `docs/development/API_REFERENCE.md`, `docs/architecture/overview.md`, `AGENTS.md` | Agent-facing docs |
| `pyproject.toml`, `mypy.ini`, `scripts/ci.sh`, `.github/workflows/ci.yml` | Exclude nested `src/deepseek-cursor-proxy` from lint/typecheck |
