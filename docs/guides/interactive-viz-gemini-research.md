# Interactive Viz — Gemini Research Notes

> **Audience:** agents extending chart rendering or notebook_run embed flow.

## Gemini app pattern

Google Gemini renders charts **natively in the chat UI** — the model does not paste image URLs or HTML in its reply. Instead:

1. The model emits a **structured chart spec** (JSON) or saves an artifact.
2. The client **auto-embeds** the visualization beside/after tool output.
3. The assistant reply stays **1–2 sentences** of insight; no markdown embed syntax.

## ADK artifact + inline Part

In the [Agent Development Kit (ADK)](https://google.github.io/adk-docs/), multimodal output uses:

- **Artifacts** — files saved to session storage (HTML, PNG, CSV).
- **inline_data Parts** — base64 blobs attached to model turns.

The UI binds artifact MIME types to renderers (image, HTML iframe, etc.) without the model repeating file paths in user-visible text.

## JSON spec + frontend render (ECharts)

Gemini's structured-output charts often use a compact JSON schema (series, axes, labels) rendered client-side with **ECharts** or similar. Benefits:

- **Token savings ~30–50%** vs embedding full Plotly HTML or base64 PNG in the reply.
- Deterministic re-render on theme/resize.
- No sandboxed iframe for pure spec-driven charts.

Trade-off: fewer Plotly-specific features (3D, statistical overlays) unless encoded in the spec.

## Owlynn mapping

| Gemini / ADK | Owlynn |
|--------------|--------|
| Artifact saved to session | `notebook_run` writes `chart.html` or `.png` to project workspace |
| Client auto-embed | `parse_chart_artifact()` → `chart_artifact` on `tool_execution` WS event |
| Inline Part MIME routing | Frontend `ConversationChartEmbed` → `ChatInteractiveChart` (HTML iframe) or `ChatImageViewer` (PNG) |
| Short assistant reply | `notebook_chart_embed_nudge` — 1–2 sentences, no `/api/files/` markdown |

### Plotly HTML iframe path

Preferred for rich interactivity today:

```python
fig.write_html(f"{WORKSPACE_DIR}/chart.html", include_plotlyjs="cdn", full_html=True)
```

Backend attaches:

```json
{
  "chart_artifact": {
    "filename": "chart.html",
    "url": "/api/files/chart.html?project_id=<id>",
    "kind": "interactive",
    "mime_type": "text/html"
  }
}
```

Frontend appends a `chart_embed` timeline item; `AppShell` renders via sandboxed iframe (`ChatInteractiveChart`).

### Future: JSON spec path

To align closer with Gemini/ECharts: have `notebook_run` emit a small JSON file (`chart.json`) and add a lightweight ECharts renderer. Reuse the same WS `chart_artifact` contract with `kind: "interactive"` and a new MIME or filename convention.

## Key files

| File | Role |
|------|------|
| `src/tools/notebook_libs.py` | `parse_chart_artifact`, `notebook_chart_embed_nudge` |
| `src/api/ws/handler.py` | Attach `chart_artifact` on `notebook_run` success |
| `frontend-v2/src/appEventHandlers.ts` | `ConversationChartEmbed`, `buildChartEmbedItem` |
| `frontend-v2/src/App.tsx` | Append `chart_embed` on tool success |
| `frontend-v2/src/components/AppShell.tsx` | Render chart timeline items |

## Agent checklist

1. Save chart via `notebook_run` (Plotly HTML preferred).
2. Do **not** put markdown image/link embeds in the final reply.
3. Summarize findings in **1–2 sentences**; the UI auto-shows the chart.
