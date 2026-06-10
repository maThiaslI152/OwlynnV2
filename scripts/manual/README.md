---
status: active
category: reference
audience: agent
---

# Manual integration scripts

Ad-hoc scripts for live API / tool smoke tests. **Not part of pytest or CI.**

| Script | Usage |
|--------|--------|
| `test_deep_research.py` | `python scripts/manual/test_deep_research.py` — live `deep_research` tool |
| `test_websearch_live.py` | `python scripts/manual/test_websearch_live.py` — live `web_search` + deep research |

Requires `.env`, LM Studio / network as appropriate.
