---
title: "StirlingPDF On-Demand Start + JVM Heap Cap"
category: changes
date: 2026-06-26
status: active
---

# StirlingPDF On-Demand Start + JVM Heap Cap

## Summary

StirlingPDF container no longer starts at boot. It spins up lazily on first PDF ingestion, then runs with a capped JVM heap. Idle memory savings: **~2 GB**.

## Motivation

StirlingPDF is a Java/Spring Boot container that consumed ~2 GB RAM 24/7 even when no PDFs were being processed. Most sessions never touch a PDF. This wasted memory on a 24 GB M4 Air where every GB counts.

## Changes

### `docker-compose.yml`

- `mem_limit: 2g` → `mem_limit: 1g`
- Added `JAVA_TOOL_OPTIONS=-Xms128m -Xmx512m` to cap JVM heap

The JVM starts with 128 MB heap and grows to max 512 MB under PDF load. Combined with the 1 GB container limit, peak usage during PDF processing is ~1 GB (was ~2 GB).

### `start.sh`

- Removed `stirling-pdf` from `_CORE_SERVICES` (was `qdrant redis stirling-pdf`, now `qdrant redis`)
- Removed the StirlingPDF health check at startup
- StirlingPDF is now started on-demand by the Python backend

### `src/integrations/stirling_pdf.py`

Added `ensure_available(timeout=30.0)` function:

1. Checks if container is already running via `is_available()`
2. If not, tries `podman compose up -d stirling-pdf` (falls back to docker-compose)
3. Polls readiness every 1s until healthy or timeout
4. Returns `True` if ready, `False` if startup failed

Pattern mirrors `vision_model_manager.py` (lazy load + readiness polling).

### `src/pdf/intake.py`

Replaced `stirling_pdf.is_available()` with `stirling_pdf.ensure_available()` in both extraction functions. This triggers container startup on first PDF ingestion.

PyMuPDF fallback handles the case where `ensure_available()` returns `False`.

### `tests/test_cloud_strict_mode.py`

Updated `test_complex_node_blocks_fallback_on_cloud_failure` to mock `get_fallback_llm` (cloud fallback change from earlier session).

## Memory Impact

| State | Before | After |
|-------|--------|-------|
| Idle (no PDFs) | ~2.0 GB | **0 MB** |
| During PDF use | ~2.0 GB | **~1.0 GB** |
| **Savings** | — | **2 GB idle, 1 GB active** |

## Flow

```
User sends PDF attachment
    → intake.py calls stirling_pdf.ensure_available()
        → is_available() → False (container not running)
        → podman compose up -d stirling-pdf
        → poll readiness (1s intervals, 30s timeout)
        → is_available() → True
    → extract_text() or ocr_then_extract()
    → PyMuPDF fallback if ensure_available() returns False
```

## Related

- [`docs/PERFORMANCE_SLOS.md`](../../PERFORMANCE_SLOS.md) — memory budget
- [`src/integrations/stirling_pdf.py`](../../../src/integrations/stirling_pdf.py) — StirlingPDF client
- [`src/pdf/intake.py`](../../../src/pdf/intake.py) — unified PDF intake
