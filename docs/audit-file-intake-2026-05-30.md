---
status: active
category: audit
last_updated: 2026-05-31
owner: human
---

# RAG File Intake Audit Report

> **Purpose:** Automated audit of the RAG file intake pipeline — PDF, DOCX, XLSX ingestion, processing, LLM retrieval, and Qdrant indexing.

**Date**: 2026-05-30  
**Auditor**: Automated audit via Cursor agent  
**Scope**: PDF, DOCX, XLSX file intake pipeline — ingestion, processing, LLM retrieval, and RAG indexing

---

## Executive Summary

| Stage | Status | Notes |
|-------|--------|-------|
| File Watcher Detection | ✅ PASS | watchdog detects files in `workspace/projects/default/` within seconds |
| PDF Extraction (PyMuPDF) | ✅ PASS | English + Thai text extracted correctly; font-dependent (see note) |
| DOCX Extraction (python-docx) | ⚠️ PASS with limitation | Paragraphs extracted; **tables not extracted** (known library limitation) |
| XLSX Extraction (pandas+tabulate) | ⚠️ PASS with limitation | Markdown table generated; merged cells produce "Unnamed" column headers |
| Processed Cache (`.processed/`) | ✅ PASS | All three files cached correctly at `workspace/.processed/` |
| LLM File Retrieval (browser) | ⚠️ PARTIAL | Agent accessed workspace but read wrong file (XLSX instead of PDF for revenue query) |
| RAG Semantic Search (Qdrant) | ✅ PASS | Manual indexing + search retrieves correct document chunks |
| Default Project Auto-Indexing | ❌ BUG CONFIRMED | Auto-indexing is intentionally skipped for default project (line 80 of server.py) |

**Overall**: The file intake pipeline **works** for all three formats, but has meaningful gaps in DOCX table extraction, LLM file selection ambiguity, and auto-indexing for the default project.

---

## Methodology

### Sample Files Created

Three controlled files with known, verifiable content were created using Python libraries:

**`audit_doc.pdf`** (2 pages, Arial Unicode font):
- Page 1: Project Omega Financial Summary — revenue ฿4,200,000, 147 clients, Bangkok office 62%, Thai text paragraph
- Page 2: Verification page with code `OWLYNN-AUDIT-2026-X7K9M` and answer "42"

**`audit_doc.docx`** (14 paragraphs, 1 table):
- 5 named components: Vector Sentinel, Memory Nexus, Knowledge Forge, Insight Prism, Truth Anchor
- Technical specifications table (Component, Version, Status, Throughput)
- Audit keyword: `BLUE-FALCON-992`

**`audit_data.xlsx`** (6 products, 3 columns):
- Products: Wireless Earbuds Pro (250×฿2,990), Mechanical Keyboard RGB (180×฿4,590), 27" 4K Monitor (45×฿12,990), USB-C Hub 7-in-1 (520×฿890), Laptop Stand Aluminum (310×฿1,590), Webcam 1080p HD (95×฿2,490)

### Test Queries

| # | Query | Expected Source | Expected Answer |
|---|-------|----------------|-----------------|
| 1 | "What was Project Omega's Q1 2026 revenue?" | audit_doc.pdf | ฿4,200,000 |
| 2 | "List the 5 items from the specification document" | audit_doc.docx | Vector Sentinel, Memory Nexus, Knowledge Forge, Insight Prism, Truth Anchor |
| 3 | "What product had the highest quantity in the inventory data?" | audit_data.xlsx | USB-C Hub 7-in-1 (520 units) |

---

## Detailed Results

### Step 1: File Creation

All three files created successfully:
- `audit_doc.pdf` — 2 pages, Arial Unicode font, 23MB (embedded font)
- `audit_doc.docx` — 14 paragraphs, 1 table, 37KB
- `audit_data.xlsx` — 6 data rows, 3 columns, 5KB

**Note**: PDF required Arial Unicode font for Thai text extraction. Default PyMuPDF built-in fonts (Helvetica) produce `????` for Thai characters.

### Step 2: Services Status

All services were already running at audit start:
- **Qdrant** (port 6333): `owlynn_qdrant` container, collection `cowork_memory_nomic`, 52 points
- **Redis** (port 6379): `owlynn_redis` container
- **Backend** (port 8000): `/api/health` → `{"status":"ok","agent":"ready"}`
- **Frontend** (port 5173): HTTP 200, Owlynn UI functional

### Step 3: Auto-Processing Verification

Files were copied to `workspace/projects/default/` at 04:25. Within 3 seconds, the file watcher detected and processed all three:

**PDF → `audit_doc.pdf.txt`:**
```
--- Page 1 ---
Owlynn RAG File Intake Audit - Controlled Sample
...
Revenue for Q1 2026 reached ฿4,200,000 (four million two hundred thousand Thai Baht),
representing a 34% increase year-over-year.
...
เอกสารนี้เป็นส่วนหนึ่งของการตรวจสอบระบบ RAG File Intake ของ Owlynn
รายได้ของโปรเจกต์โอเมก้าในไตรมาสที่ 1 ปี 2026 อยู่ที่ 4.2 ล้านบาท
...
--- Page 2 ---
VERIFICATION-CODE: OWLYNN-AUDIT-2026-X7K9M
...
The answer to the ultimate question of life, the universe, and everything
as stated in this audit document is: 42
```
✅ All key content extracted. Thai text preserved.

**DOCX → `audit_doc.docx.txt`:**
```
1. Vector Sentinel — Real-time embedding synchronization engine
2. Memory Nexus — Long-term context preservation layer with temporal weighting
3. Knowledge Forge — Multi-format document ingestion and structuring pipeline
4. Insight Prism — Semantic query decomposition and parallel retrieval router
5. Truth Anchor — Hallucination detection and fact-verification module
```
✅ Paragraphs extracted. ⚠️ Technical specifications **table data missing** — python-docx only extracts paragraphs.

**XLSX → `audit_data.xlsx.md`:**
```
| Owlynn Inventory Audit — Q1 2026   | Unnamed: 1   | Unnamed: 2   |
|:-----------------------------------|:-------------|:-------------|
| nan                                | nan          | nan          |
| Product                            | Quantity     | Price (THB)  |
| Wireless Earbuds Pro               | 250          | 2990         |
| Mechanical Keyboard RGB            | 180          | 4590         |
| 27" 4K Monitor                     | 45           | 12990        |
| USB-C Hub 7-in-1                   | 520          | 890          |
| Laptop Stand Aluminum              | 310          | 1590         |
| Webcam 1080p HD                    | 95           | 2490         |
```
⚠️ Merged title cell produces `Unnamed: 1` / `Unnamed: 2` column headers and a `nan` row. Data rows are correct.

### Step 4: Browser LLM Audit

**Test Query 1**: "What was Project Omega's Q1 2026 revenue?"

The Owlynn agent entered a **Router Skill Ambiguity** HITL state, requiring manual selection of "Work with local files". After routing:
- Agent accessed workspace files via `read_workspace_file`
- **Bug**: Agent read `audit_data.xlsx` instead of `audit_doc.pdf`
- Agent attempted to calculate revenue by summing product prices from inventory (incorrect approach)
- The PDF contained the direct answer: "฿4,200,000"

**Root cause**: The agent saw "Q1 2026" in both the XLSX title ("Owlynn Inventory Audit — Q1 2026") and chose the wrong file. The agent did not prioritize the PDF which had the explicit revenue statement.

**Assessment**: File retrieval mechanism works, but **semantic file selection is unreliable** when multiple files contain related keywords. The agent cannot distinguish between "inventory audit for Q1 2026" and "Project Omega Q1 2026 revenue summary."

### Step 5: RAG Semantic Search

**Manual Indexing**: All three files indexed via `POST /api/projects/default/knowledge`:
```json
{"status":"ok","message":"Indexed audit_doc.pdf into project knowledge base"}
{"status":"ok","message":"Indexed audit_doc.docx into project knowledge base"}
{"status":"ok","message":"Indexed audit_data.xlsx into project knowledge base"}
```

**Semantic Search** (`/api/mem0/search?query=Project+Omega+revenue+Q1+2026&project_id=default`):
- **Top result**: PDF content — "Revenue for Q1 2026 reached ฿4,200,000" ✅
- **2nd result**: XLSX content — inventory table
- **3rd result**: DOCX content — technical specification

✅ RAG search correctly ranks the most semantically relevant document chunk first.

---

## Bugs Found

### 1. ❌ Default Project Auto-Indexing Skipped (Confirmed)

**Location**: `src/api/server.py` line ~80  
**Description**: `notify_file_processed()` looks for cache at `workspace/projects/{id}/.processed/` but the file watcher writes to `workspace/.processed/` (global). Non-default project auto-indexing into Qdrant is silently broken — the per-project `.processed/` directory never exists. Default project auto-indexing is intentionally skipped.  
**Impact**: Files in `workspace/projects/default/` are processed to `.processed/` cache but never indexed into Qdrant automatically.  
**Workaround**: Manual indexing via `POST /api/projects/{id}/knowledge`.

### 2. ⚠️ DOCX Table Extraction Missing

**Location**: `src/api/file_processor.py` — uses `python-docx` paragraph extraction only  
**Description**: `python-docx` does not extract table content. The technical specifications table in `audit_doc.docx` (Component, Version, Status, Throughput columns) is completely absent from the processed output.  
**Impact**: Any structured data in DOCX tables is invisible to LLM and RAG search.  
**Recommendation**: Upgrade to Docling (see Technology Recommendations below).

### 3. ⚠️ XLSX Merged Cell Handling

**Location**: `src/api/file_processor.py` — uses `pandas.read_excel()` + `tabulate`  
**Description**: Merged cells in XLSX produce `Unnamed: N` column headers and `NaN` rows. The inventory title row ("Owlynn Inventory Audit — Q1 2026") creates an empty data row and unnamed columns.  
**Impact**: Minor — data rows are still correct, but header quality is degraded.

### 4. ⚠️ Agent File Selection Ambiguity

**Location**: Agent router (LLM-driven file selection)  
**Description**: When multiple files contain related keywords, the agent may choose the wrong file. In this audit, the agent read XLSX inventory data instead of the PDF financial summary for a revenue query.  
**Impact**: LLM answers may be based on incorrect file context.

### 5. ℹ️ Minor Issues (from code audit)

| Issue | Location | Impact |
|-------|----------|--------|
| `processing_lock` initialized but never acquired | `file_processor.py:48` | Dead code |
| `fitz.open()` not in context manager | `file_processor.py:159` | Resource leak on PDF exception |
| Fuzzy filename match in two directions | `core_tools.py:59` | False positive filename matches |

---

## Technology Recommendations

### Docling — Recommended Upgrade for PDF/DOCX

| Format | Current | Limitation | Docling |
|--------|---------|------------|---------|
| PDF | PyMuPDF (`page.get_text()`) | No layout/reading-order/table structure | TableFormer 97.9% TEDS, semantic hierarchy |
| DOCX | python-docx (paragraphs only) | No tables, no hierarchy | Full DOCX→structured markdown with tables |

**Docling advantages**:
- Single API for PDF, DOCX, PPTX, XLSX, HTML — replaces 4+ libraries
- Semantic hierarchy: typed nodes (section_header, list_item, table, picture, code) with level + page provenance
- MLX acceleration on Apple Silicon, ~3.1 s/page on CPU
- Built-in MCP server (`docling serve`)
- Fully local, zero API costs — aligns with Owlynn's local-first architecture

**Integration approach**: Use `docling` standalone in `file_processor.py`:
```python
from docling.document_converter import DocumentConverter
```
Skip `langchain-docling` (needs `langchain-core ~=1.0`, Owlynn is `>=0.3`).

### XLSX — Keep Current Approach

The pandas + tabulate markdown approach works well. The merged cell issue is cosmetic. No library change needed.

### Notable MCP Servers for Future Consideration

| MCP Server | Role | Fit for Owlynn |
|------------|------|----------------|
| **Docling MCP** (built-in) | Multi-format → structured Markdown/JSON | Replace file watcher extraction layer |
| **Markdownify MCP** | 29+ formats → Markdown, zero ML deps | Lightweight alternative, no GPU needed |
| **pdf-mcp** | PDF-specialized, hybrid BM25+semantic search | Augment Qdrant with keyword search |
| **claude_document_mcp_server** | Office file CRUD (create/edit DOCX/XLSX) | Agent-driven document creation |

---

## Frontend Gap Analysis

**Confirmed**: No drag-and-drop or file upload UI exists in the frontend (`Composer.tsx`). Files can only enter the workspace via:
1. Filesystem: Manually placing files in `workspace/projects/{id}/`
2. REST API: `POST /api/upload`

No `<input type="file">`, `onDrop`/`onDragOver` handlers, paste handler, or `FormData` upload logic was found. This is a known gap documented in the plan.

---

## What Works Correctly

- File watcher detection + processing (all formats tested)
- `.processed/` cache output at `workspace/.processed/`
- `read_workspace_file` cache lookup (resolves to `workspace/.processed/`)
- WebSocket `file_status` broadcast
- Upload API (`POST /api/upload`) + auto-index
- RAG semantic search (when manually indexed)
- PDF Thai+English mixed content extraction (with proper font)

---

## Audit Raw Data

### Processed Output Files

- `workspace/.processed/audit_doc.pdf.txt` — 1,787 bytes, 2 pages, Thai+English
- `workspace/.processed/audit_doc.docx.txt` — 862 bytes, paragraphs only
- `workspace/.processed/audit_data.xlsx.md` — 479 bytes, markdown table

### Sample Files

- `workspace/projects/default/audit_doc.pdf` — 23MB (Arial Unicode embedded)
- `workspace/projects/default/audit_doc.docx` — 37KB
- `workspace/projects/default/audit_data.xlsx` — 5KB

### RAG Indexing

- PDF indexed: ✅ (via `POST /api/projects/default/knowledge`)
- DOCX indexed: ✅
- XLSX indexed: ✅
- Auto-indexing: ❌ (skipped for default project)

---

## RAG System Location Map

Where each component of the RAG file intake pipeline lives in the codebase:

| Stage | Component | File | Key Lines / Function |
|-------|-----------|------|----------------------|
| 1. **Detection** | File watcher (watchdog) | `src/api/file_processor.py` | `FileWatcherHandler` (L32), `start_watcher()` (L594) |
| 2. **Extraction** | PDF → text | `src/api/file_processor.py` | `_process_pdf()` (L157), uses `fitz` (PyMuPDF) |
| | DOCX → text | `src/api/file_processor.py` | `_process_word()` (L183), uses `python-docx` |
| | XLSX → markdown | `src/api/file_processor.py` | `_process_table()` (L169), uses `pandas` + `tabulate` |
| 3. **Cache** | Write `.processed/` | `src/api/file_processor.py` | `process_file()` (L87), outputs to `workspace/.processed/` |
| 4. **Indexing** | Auto-index into Qdrant | `src/api/server.py` | `notify_file_processed()` (L51), auto-index hook (L73-121) |
| | Manual index API | `src/api/server.py` | `POST /api/projects/{id}/knowledge` (L1136) |
| | Project knowledge mgr | `src/memory/project.py` | `project_manager.add_knowledge()` |
| 5. **Retrieval** | File cache lookup | `src/tools/core_tools.py` | `read_workspace_file()` (L47), cache-first at L69-81 |
| | Semantic search | `src/tools/rag_tools.py` | `search_workspace_docs()` (L15), via Mem0/Qdrant |
| | Search API | `src/api/server.py` | `GET /api/mem0/search` (L522) |
| 6. **Ingestion** | Upload API | `src/api/server.py` | `POST /api/upload` (L1021) |
| | Auto-index on upload | `src/api/server.py` | `_auto_index_project_file()` (L1058) |
| 7. **LLM Access** | Message content builder | `src/api/server.py` | `build_message_content()` (L1841), PDF inline (L1879) |
| | Vision routing | `src/agent/router/feature_extractor.py` | `_has_image_content` (L68), vision keywords (L53) |
| 8. **Storage** | Vector store | Docker: `qdrant/qdrant` | Collection: `cowork_memory_nomic`, 768-dim nomic embeddings |
| | Memory manager | `src/memory/long_term.py` | `mem0_memory` singleton |

### Data Flow

```
File placed in workspace/projects/{id}/
        │
        ▼
[FileWatcherHandler] watchdog detects new file
        │
        ▼
[file_processor.process_file()] routes by extension
        │
        ▼
[_process_pdf / _process_word / _process_table] extracts text
        │
        ▼
workspace/.processed/{filename}.txt (or .md)
        │
        ├──▶ [read_workspace_file tool] agent cache-lookup
        │
        └──▶ [notify_file_processed] WS broadcast + auto-index
                 │
                 ▼
            [project_manager.add_knowledge()] chunks → Qdrant
                 │
                 ▼
            [search_workspace_docs tool] semantic RAG retrieval
```

---

## Recommendations Summary

1. **Immediate**: Fix auto-indexing cache path mismatch so non-default projects auto-index into Qdrant
2. **Short-term**: Add DOCX table extraction (either enhance python-docx usage or adopt Docling)
3. **Short-term**: Fix XLSX merged cell handling (skip empty title rows)
4. **Medium-term**: Adopt Docling for unified PDF/DOCX/PPTX extraction with semantic hierarchy
5. **Medium-term**: Add drag-and-drop file upload UI to frontend
6. **Long-term**: Implement agent file disambiguation (metadata hints, explicit file references)


## Related

- [`docs/STATUS.md`](STATUS.md) — project status and risks
- [`docs/BUG-ANALYSIS.md`](BUG-ANALYSIS.md) — bug analysis

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter, purpose blockquote
