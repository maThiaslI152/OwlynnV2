# Multi-model review fixes (2026-06-16)

Adversarial review follow-up: security, privacy, documentation, and competitive-positioning fixes from GPT-5.5, Gemini 3 Flash, and Claude Opus reviewers.

## Critical — fixed

| Issue | Fix |
|-------|-----|
| Unauthenticated `/api/notebook/run` + `CORS *` drive-by RCE | Loopback-only token (`GET /api/local-run-token`, header `X-Owlynn-Run-Token`); CORS restricted to localhost Vite/backend origins (`src/api/local_auth.py`) |
| Model-authored runnable cells without gate | `cell` blocks default `runnable: false`; Run requires confirm dialog + token (`InteractiveCell.tsx`) |
| Arbitrary embed URLs | `InteractiveEmbed` only allows `/api/files/` workspace paths |

## Privacy — fixed

| Issue | Fix |
|-------|-----|
| Deterministic placeholder hashes correlate secrets across turns | Session-local random suffix per placeholder (`anonymization.py`) |
| Raw `thread_id` sent to DeepSeek `user` field | Hashed fingerprint via `cloud_user_fingerprint()` (`cloud_privacy.py`, `complex.py`) |
| Overclaim “PII scrub” | Module doc + architecture overview reframed as **best-effort** hybrid |

## Documentation — fixed

| Issue | Fix |
|-------|-----|
| API mode sensitive tools doc wrong | `docs/HITL.md` — deny unless `auto_approve_sensitive` |
| “Cloud-primary / all data on Mac” confusion | `docs/architecture/overview.md` — privacy-first hybrid wording |
| Memory cap 6k vs 12k conflict | `docs/MEMORY.md` clarifies 12000 char injection cap |

## Deferred (not in this pass)

- Full notebook sandbox (container/macOS sandbox) — subprocess isolation only; document risk in `docs/TOOLS.md`
- Lite mode / hardware profiles in `defaults.yaml`
- NER-based anonymization (Presidio)
- Cloud preview UI (“what left the device”)
- Voice input, artifact canvas, expanded frontier A/B eval (n≥30)
- Response coherence gate (R5)
- Stale `SOTA_FEATURES_GUIDE.md` full rewrite

## Verify

```bash
./scripts/ci.sh --quick
pytest tests/test_notebook_api.py tests/test_local_auth.py tests/test_cloud_privacy.py tests/test_anonymization.py -q
```
