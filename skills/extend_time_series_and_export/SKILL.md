---
name: extend_time_series_and_export
category: data
description: Procedural skill synthesized from user workflow
triggers: [extend_time_series_and_export]
version: '1.0'
---
# Extend a trend graph with earlier periods
When you need to show a longer historical trend than the current chart:
1. Add rows for preceding years directly into your source dataset.
2. Re-render the plot — the x-axis will automatically expand to include them.
3. Export the full tabular data as an xlsx file (`export_to_excel`) so it can be shared or used in other tools.