---
name: html_comparison_chart
category: data
description: Offline Chart.js HTML bar/line/pie charts for pre-known comparison data
triggers: [html_comparison_chart, comparison chart, bar chart html, price comparison chart]
version: '1.0'
---
# HTML Comparison Chart (Offline Chart.js)

Use this skill when the user provides numbers to compare (prices, benchmarks, scores) and wants a polished chart without Python or matplotlib.

**Script URL:** `/vendor/chart.umd.min.js` — Owlynn-bundled Chart.js 4.4.1, works offline. **Never use a CDN.**

## A. Offline Chart.js template (default)

Save via `write_workspace_file` as a `.html` file:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{TITLE}}</title>
<script src="/vendor/chart.umd.min.js"></script>
<style>
  body { font-family: system-ui, sans-serif; margin: 1rem; background: #0f1117; color: #e8eaed; }
  .wrap { max-width: 640px; }
  .css-fallback { display: none; }
</style>
</head>
<body>
<div class="wrap"><canvas id="chart"></canvas></div>
<script>
new Chart(document.getElementById('chart'), {
  type: 'bar',
  data: {
    labels: {{LABELS_JSON}},
    datasets: [{ label: '{{METRIC}}', data: {{VALUES_JSON}},
      backgroundColor: ['#4a90d9','#f5a623','#d0021b','#7ed321','#bd10e0','#50e3c2'] }]
  },
  options: { indexAxis: 'y', responsive: true,
    plugins: { legend: { display: false } } }
});
</script>
</body></html>
```

Replace `{{TITLE}}`, `{{METRIC}}`, `{{LABELS_JSON}}` (e.g. `["A","B","C"]`), and `{{VALUES_JSON}}` (e.g. `[1.0, 1.15, 1.30]`) with the user's data.

Embed in your reply: `[{{TITLE}}](/api/files/{{FILENAME}}.html?project_id=default)`

## B. Pure CSS fallback (last resort)

Use only if Chart.js cannot load. No external dependencies:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{TITLE}}</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 1rem; background: #0f1117; color: #e8eaed; }
  .bar-row { display: flex; align-items: center; margin: 0.5rem 0; gap: 0.75rem; }
  .bar-label { width: 8rem; text-align: right; font-size: 0.875rem; }
  .bar-track { flex: 1; background: #2a2d35; border-radius: 4px; height: 1.5rem; }
  .bar-fill { height: 100%; border-radius: 4px; background: #4a90d9; }
  .bar-value { width: 3rem; font-size: 0.875rem; }
</style>
</head>
<body>
<h2>{{TITLE}}</h2>
<!-- Repeat .bar-row per category; width % = value / max * 100 -->
<div class="bar-row">
  <span class="bar-label">Category</span>
  <div class="bar-track"><div class="bar-fill" style="width:75%"></div></div>
  <span class="bar-value">1.0x</span>
</div>
</body></html>
```

## Rules

- One `write_workspace_file` call — do not use `notebook_run` unless the user explicitly asks for matplotlib/PNG/Python.
- Plot user-provided numbers directly; do not calculate unless asked.
- Horizontal bar: Chart.js `type: 'bar'` with `indexAxis: 'y'`.
