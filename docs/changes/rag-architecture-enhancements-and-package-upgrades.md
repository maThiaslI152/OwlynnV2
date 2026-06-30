# RAG Architecture Enhancements & Dependency Upgrades

Date: 2026-07-01

## 1. RAG Architecture Upgrades
We made significant improvements to Owlynn's hybrid search Knowledge Library (RAG) system to increase both speed and semantic accuracy:

- **BM25 Keyword Search:** Replaced naive keyword substring/counting scoring in `src/tools/rag_tools.py` with a lightweight, mathematically rigorous Python implementation of the BM25 algorithm. This properly handles Term Frequency and Inverse Document Frequency to prioritize rare keywords and ignore common stop-words.
- **Smart Delta-Indexing:** Added an MD5 hashing layer in `src/memory/vector_lifecycle.py`. The system now generates an MD5 hash of raw file contents and checks it against a `.processed/hashes.json` registry before performing vectorization. This allows unchanged files to bypass the heavy Qdrant/LM Studio embedding step during project re-indexing.
- **Syntax-Aware Chunking:** Swapped arbitrary string slicing for Langchain's `RecursiveCharacterTextSplitter`. Chunks are now broken cleanly along double newlines, single newlines, and spaces, preserving function boundaries and semantic blocks without arbitrary character cut-offs.

## 2. Environment Upgrades
- Ran a massive environment upgrade (`pip list --outdated | xargs pip install --upgrade`), bumping over 100 packages including `langchain`, `fastapi`, `numpy`, `playwright`, and `pip` to their latest available wheel versions.
- Generated a new `requirements.txt` via `pip freeze` to accurately lock the new dependency tree.

## 3. Stability Fixes
- Fixed a type hint error in `src/memory/pentest_engagement.py` (`any` -> `typing.Any`).
- Fixed failing unit tests in `tests/test_phase3_screen_assist.py` by adding newly registered pentest tools (`kali_tmux_list_windows`, `kali_reset_vm`, `send_kali_input`, `kali_tmux_new_window`) to the `SCREEN_ASSIST_TOOLS` registry check.
- Standardized code style across 17 modified files using `ruff format`.
