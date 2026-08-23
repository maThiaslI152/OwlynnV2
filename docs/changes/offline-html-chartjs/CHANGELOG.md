# Changelog: Offline HTML/Chart.js Local Visualization (v0.2.3)

**Date:** 2026-08-23  
**Status:** Completed  
**Version:** 0.2.3

---

## Summary

Local chart generation for price/performance comparisons now defaults to **offline HTML + vendored Chart.js** via a single `write_workspace_file` call — no CDN, no `notebook_run` unless the user explicitly asks for matplotlib/PNG/Python.

---

## Key Changes

### A. Vendored Chart.js (`assets/vendor/`)
- Pinned **Chart.js 4.4.1** UMD build at `assets/vendor/chart.umd.min.js`
- Download script: `scripts/vendor_chartjs.sh` (hooked in `setup.sh`)
- Served at **`GET /vendor/chart.umd.min.js`** via FastAPI static mount

### B. Local prompt + skill
- `_LOCAL_HTML_CHART_GUIDANCE` in `src/agent/core/complex_prompt.py` — offline script URL only
- New skill: `skills/html_comparison_chart/SKILL.md` (Chart.js template + pure CSS fallback)

### C. Config
- `visualization.chartjs_local_url` and `chartjs_version` in `defaults.yaml`

### D. Auto-embed
- `parse_chart_artifact()` accepts `"written to"` tool output
- WS handler attaches `chart_artifact` on `write_workspace_file` success for `.html` files

### E. E2E
- Step E uses `python_benchmarks.html` + `/vendor/chart.umd.min.js` (180s timeout)

### G. Version & packaging (v0.2.3)
- Bumped `frontend-v2/package.json`, `pyproject.toml`, and `frontend-v2/src/test-setup.ts` to **0.2.3**
- Built macOS artifacts: `frontend-v2/dist/Owlynn-0.2.3-arm64.dmg` (~159 MB)
- Fixed `GraphNode.fx`/`fy` TypeScript types in `MindmapCanvas.tsx` for electron-builder

---

## Files

| Path | Change |
|------|--------|
| `assets/vendor/chart.umd.min.js` | Vendored Chart.js 4.4.1 |
| `scripts/vendor_chartjs.sh` | Download/pin script |
| `src/api/server.py` | `/vendor` mount |
| `src/agent/core/complex_prompt.py` | Offline HTML chart guidance |
| `skills/html_comparison_chart/SKILL.md` | Template skill |
| `src/config/defaults.yaml` | `visualization.*` |
| `src/tools/notebook_libs.py` | `parse_chart_artifact` "written to" |
| `src/api/ws/handler.py` | chart_artifact on write_workspace_file |
| `scratch/test_mindmap_search_graph_e2e.py` | Chart.js Step E |
| `tests/test_vendor_chartjs.py` | Vendor endpoint test |
| `tests/test_chart_artifact_write_workspace.py` | Artifact parse test |

---

## Usage (personal Mac, offline)

Ask Owlynn:

> Compare these GPU prices: RTX 4060 $299, RTX 4070 $549, RTX 4080 $999. Save as `gpu_prices.html` using Chart.js from /vendor/chart.umd.min.js. Use write_workspace_file only.

Chart renders in chat iframe with no network required.
