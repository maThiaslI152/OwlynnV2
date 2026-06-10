---
status: archive
category: reference
audience: agent
---

# Archived one-off scripts

Historical debugging / patch scripts from early 2026 stabilization. **Not used in CI or startup.**

| File | Purpose |
|------|---------|
| `audit_logs.py` | AST scan for silent `except Exception` handlers |
| `fix_tests.py` | One-time test repair helper |
| `patch_complex.py` | Ad-hoc `complex.py` patch |
| `patch_silent.py` | Silent-exception patch experiment |
| `patch_store.py` | Store patch experiment |

Run from repo root only if you know why: `python scripts/archive/<file>.py`
