# Phase 2 Architectural Upgrades

Date: 2026-06-06

## Architectural Updates
1. **Web RAG Reranking**: `deep_research` now uses `Crawl4AI` to scrape websites. The resulting Markdown is processed through the local Web RAG embeddings to chunk and rank relevance when the length exceeds 1,800 characters.
2. **Prompt Injection Defense**: All external content ingested via `deep_research` is now sandboxed in strict `<web_context>` XML tags. The router/complex node has explicit instructions to NEVER execute commands hidden in this block.
3. **Global Logging Audit**: Replaced 86 instances of anti-pattern `logging.debug("Silent error suppressed...")` with `logger.warning("Error suppressed...")` globally across API and Agent routing logic to comply with `docs/standards/coding-style.md`.
4. **CI/CD Speedup**: The GitHub Actions `.github/workflows/ci.yml` was modified so the heavy macOS Electron build only fires when pushing or merging to `main`, significantly speeding up normal PRs.
