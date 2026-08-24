---
status: active
category: reference
last_updated: 2026-08-24
owner: ai-agent
audience: agent
---

# Tools Reference

> **Purpose:** Reference for all agent tools organized by toolbox category. Tools are dynamically bound per turn based on router classification.

## Overview

Tools are organized into toolbox categories managed by `ToolRegistry`. The Router selects which categories are needed per turn, and only the relevant tools are bound to the LLM — saving ~2000 tokens of schema overhead. Tool schemas are deterministically sorted to maintain KV cache stability.

## Entry Points

```text
src/tools/registry.py             # ToolRegistry (dynamic discovery, check_fn gating, error bounding)
src/agent/tool_sets.py            # TOOLBOX_REGISTRY, resolve_tools()
src/tools/                        # Tool implementations (@tool and @registry.register)
src/agent/core/complex_prompt.py   # Deterministic tool sorting and guidance assembly
src/agent/core/complex_tool_action.py # Parallel tool execution and bounded outputs
src/agent/nodes/security_proxy.py  # SENSITIVE_TOOLS set
src/api/routes/files.py            # Tool discovery (GET /api/tools)
```

## Architecture

### Tool Selection Flow

1. Router classifies the user request into one or more toolbox categories
2. `resolve_tools(toolbox_names, web_search_enabled)` returns the union of tools from selected categories + always-included tools
3. `complex_llm_node` binds only the resolved tools to the LLM (after web-budget filter + embedding rerank)
4. Local-first routing picks a **narrow** toolbox (`web_search`, `file_ops`, `data_viz`, `screen_assist`, or lean default `web_search`+`memory`+`productivity`) — never an implicit `["all"]`
5. `"all"` is reserved for empty-state fallback and explicit HITL “Others”; it is a **lean chat core** (web + memory + notebook/docs/todos/skills + `render_interactive_block` + `ask_user`). Screen-assist and ipynb tools stay on named `screen_assist` / `data_viz` toolboxes only

## API

### Always Included

| Tool | Description |
|------|-------------|
| `ask_user` | Ask a clarifying question. Supports 1-3 choice buttons + free text. Always bound regardless of toolbox selection |

### Toolbox: `web_search`

| Tool | Description |
|------|-------------|
| `web_search` | Search via SearXNG/DDG/Bing. Supports `focus_query` for reranking |
| `fetch_webpage` | Fetch URL content. Embedding-ranked excerpts with `focus_query` |
| `deep_research` | Exhaustive search and async concurrent crawling via Crawl4AI. Outputs `<web_context>`-sandboxed Markdown. Uses Web RAG if output exceeds length thresholds. |

### Toolbox: `file_ops`

| Tool | Description |
|------|-------------|
| `read_workspace_file` | Read file content. PDF via StirlingPDF → OCR → PyMuPDF (`src/pdf/intake.py`); DOCX via Docling. Cache-first under `<project>/.processed/`. Strips `[Attached: …]` / `Attached:` wrappers from LLM filenames. Fuzzy filename matching |
| `write_workspace_file` | Create or overwrite a file |
| `edit_workspace_file` | Search-and-replace in a file. Exact pattern match required |
| `list_workspace_files` | List directory contents with file sizes |
| `delete_workspace_file` | Delete a file |
| `download_to_workspace` | Download a file from a URL directly into the isolated workspace directory. SSRF-protected via `url_policy.py` (blocks private IPs, localhost, cloud metadata) |
| `upload_from_workspace` | Force an `<input type="file">` upload to a browser tab using Playwright CDP bypass (registered via `SCREEN_ASSIST_TOOLS`) |

### Toolbox: `data_connectors`

| Tool | Description |
|------|-------------|
| `ingest_github_repo` | Ingest and index a GitHub repository |
| `ingest_youtube_transcript` | Ingest and index a YouTube video transcript |
| `ingest_obsidian_vault` | Ingest and index an Obsidian markdown vault |

### Toolbox: `data_viz`

| Tool | Description |
|------|-------------|
| `create_docx` | Word document with headings, bullets, numbered lists |
| `create_xlsx` | Excel spreadsheet from CSV-like text. First row = headers |
| `create_pptx` | PowerPoint with slides separated by `---` |
| `create_pdf` | PDF from text content via PyMuPDF |
| `notebook_run` | Stateful Python REPL (HITL-gated). Variables persist between calls. **Sandboxed** — `requests`, `httpx` removed from import whitelist; only safe stdlib + data science modules allowed. Inline chat Run uses `POST /api/notebook/run` (loopback token required). |
| `notebook_reset` | Clear all notebook variables |
| `notebook_vars` | List variables in the notebook session |
| `read_ipynb` | Read workspace `.ipynb` and summarize cells |
| `write_ipynb` | Create/update workspace `.ipynb` from JSON cell array |
| `export_ipynb_html` | Export notebook to HTML via nbconvert (when installed) |
| `render_interactive_block` | Validate payload and return inline chat widget fence (quiz, steps, callout, embed, cell) |

### Local HTML charts (offline, Gemma 12B default)

For price/performance/benchmark comparisons with **pre-known values**, the local model should **not** use `notebook_run`. Instead:

1. Call `write_workspace_file` with a self-contained `.html` file
2. Load vendored Chart.js: `<script src="/vendor/chart.umd.min.js"></script>` (offline, no CDN)
3. Embed in reply: `[Title](/api/files/chart.html?project_id=default)`

Skill template: `skills/html_comparison_chart/SKILL.md` via `invoke_skill`.  
Config: `visualization.chartjs_local_url` in `defaults.yaml`.  
Use `notebook_run` only when the user explicitly asks for matplotlib, PNG, Python, or dataset computation.

### Toolbox: `productivity`

| Tool | Description |
|------|-------------|
| `todo_add` | Add task with priority (low/medium/high) |
| `todo_list` | List tasks. Filter by status (all/pending/done) |
| `todo_complete` | Mark a task as done |
| `list_skills` | List available skill templates from `skills/` directory |
| `invoke_skill` | Load and return a skill's prompt template |
| `skill_view` | View skill metadata, instructions, and package support files (`references/`, `templates/`, `scripts/`) |
| `skill_manage` | Author, create, or update skill packages and support files |
| `render_interactive_block` | Build validated inline widget fences for chat UI |

### Toolbox: `study`

| Tool | Description |
|------|-------------|
| `course_register` | Register course code, name, exam date, linked PDFs. Auto-creates workspace project when files provided. |
| `course_workspace_create` | On-demand workspace creation for existing course |
| `course_chat_create` | Create named chat in course project (e.g., "Chapter 1") |
| `course_list` / `course_get` | List or fetch course metadata |
| `study_note_save` / `study_note_search` | Structured study notes CRUD/search |
| `flashcard_deck_create` / `flashcard_review` | Flashcard decks with SM-2 lite scheduling |
| `flashcard_suggest` | Generate flashcard content from course files |
| `quiz_session_start` / `quiz_session_answer` | Thread-scoped multi-question quizzes |
| `study_session_log` | Log study sessions for streak tracking |
| `study_weak_areas` | Detect weak topics from misconception history |
| `mastery_record` | Explicit study misconception/mastery LTM atoms |
| `export_study_sheet` | Export study guide to PDF or DOCX |

Study skills (`study_tutor`, `exam_prep`, `flashcard_builder`, `interactive_teaching`, etc.) bind `file_ops` + `memory` + `study` toolboxes. Learning mode (`response_style: learning`) activates study scenario automatically.

**Inline widgets:** `interactive_teaching` skill + `render_interactive_block` produce `owlynn-*` fences rendered inline in chat (see `docs/CHAT_PROTOCOL.md`).

**Study mode:** See [MODES.md](MODES.md) for mode system. See [STUDY.md](STUDY.md) for full study system documentation.

### Toolbox: `pentest`

Pentest tools are curated — no study tools, no global memory tools. All tools that accept target IPs/hosts are decorated with `@scope_validated` for automatic scope enforcement against the active engagement.

#### Engagement Management

| Tool | Description |
|------|-------------|
| `engagement_create` | Create a new pentest engagement (name, client, description) |
| `engagement_set_phase` | Set phase: scope/recon/exploit/report/completed. Auto-starts StirlingPDF on report phase |
| `engagement_data_set` / `engagement_data_get` | Save/retrieve engagement data (temp passwords, hints) |
| `engagement_notes` | Read or write engagement notes |
| `engagement_report` | Generate MD or PDF report |
| `engagement_compare` | Compare findings across multiple engagements |

#### Findings & Targets

| Tool | Description |
|------|-------------|
| `finding_add` | Add finding with full metadata (severity, CVSS, CWE, CVE, OWASP, remediation) |
| `finding_list` | List findings with optional severity/status filters |
| `finding_update` | Update finding status or remediation |
| `target_add` | Add/update a discovered host (IP, hostname, ports, OS) |
| `target_list` | List all discovered hosts |

#### Credentials & Evidence

| Tool | Description |
|------|-------------|
| `credential_store` | Store credential (encrypted at rest via Fernet) |
| `credential_list` | List credentials (usernames only, no passwords) |
| `evidence_store` | Store workspace file as evidence (SHA-256 hashed, immutable) |
| `evidence_list` / `read_evidence` | List/read evidence files |

#### Attack Chain & Intelligence

| Tool | Description |
|------|-------------|
| `suggest_next_steps` | AI-suggested next pentest steps based on engagement state |
| `auto_recon` | Automated recon plan generation |
| `analyze_attack_surface` | Analyze targets for high-value targets and attack chains |

#### Network Scanning

| Tool | Description |
|------|-------------|
| `nmap_scan` | Full nmap scanning (quick/default/full/vuln/stealth) |
| `masscan_scan` | High-speed port scanning |
| `service_enum` | Service enumeration (auto/http/smb/ssh/ftp/dns) |

#### Web Application

| Tool | Description |
|------|-------------|
| `nikto_scan` | Web server vulnerability scanning |
| `gobuster_scan` | Directory/DNS/vhost brute-force |
| `sqlmap_scan` | SQL injection detection/exploitation |
| `header_check` | HTTP security header analysis |

#### Vulnerability Scanning

| Tool | Description |
|------|-------------|
| `nuclei_scan` | Template-based vulnerability scanning |
| `searchsploit` | Exploit-DB search (read-only) |
| `cve_lookup` | NVD API CVE lookup with CVSS parsing (read-only) |

#### Exploitation

| Tool | Description |
|------|-------------|
| `metasploit_run` | Run Metasploit modules via tmux |
| `poc_validate` | PoC validation (curl/python/command) with destructive pattern blocking |

#### Post-Exploitation

| Tool | Description |
|------|-------------|
| `privesc_check` | Privilege escalation enumeration (Linux/Windows) |
| `credential_harvest` | Search for credentials/secrets on compromised host |

#### OSINT

| Tool | Description |
|------|-------------|
| `subfinder` | Subdomain enumeration |
| `shodan_search` | Shodan device/port search |
| `censys_search` | Censys host/certificate search |

#### Active Directory

| Tool | Description |
|------|-------------|
| `bloodhound_run` | AD attack path analysis |
| `kerberoast` | Kerberos service ticket extraction |
| `ldap_enum` | LDAP enumeration (users/groups/computers/OUs/trusts) |

#### Password Attacks

| Tool | Description |
|------|-------------|
| `hydra_attack` | Network login brute-force |
| `john_crack` | Password hash cracking |

#### Cloud

| Tool | Description |
|------|-------------|
| `s3_enum` | S3 bucket enumeration and access testing |

#### Reporting

| Tool | Description |
|------|-------------|
| `poc_generator` | Generate PoC scripts (SQLi, XSS, SSRF, RCE, LFI, generic) |
| `cvss_calculator` | CVSS v3.1 score calculation |
| `compliance_mapper` | Map findings to OWASP Top 10, CWE, MITRE ATT&CK |

#### Wireless

| Tool | Description |
|------|-------------|
| `wifi_scan` | Scan WiFi networks (read-only) |
| `wifi_deauth` | Deauth frames — **REQUIRES HITL** |
| `wifi_handshake_capture` | Capture WPA handshake — **REQUIRES HITL** |
| `wifi_crack_handshake` | Crack handshake offline (read-only) |
| `wifi_analyze_pcap` | Analyze pcap for wireless metadata (read-only) |
| `wifi_wps_scan` | Scan for WPS-enabled APs (read-only) |

#### Burp Suite MCP

| Tool | Description |
|------|-------------|
| `burp_scan_target` | Launch active/passive/crawl scan |
| `burp_get_issues` | Retrieve scan findings |
| `burp_get_scan_status` | Check scan progress |

**Total: 56+ pentest tools** across 11 categories. See [PENTEST.md](PENTEST.md) for full pentest architecture documentation.

### Toolbox: `memory`

| Tool | Description |
|------|-------------|
| `recall_memories` | Search short-term (JSON) memory — keyword overlap on recent 50 entries |
| `recall_all_memories` | Deep semantic search of Mem0/Qdrant vector store (long-term memory). Optional `project_id` for scoping |
| `forget_memory` | Delete specific memories by their ID (hash). Use `recall_all_memories` first to find IDs |
| `search_workspace_docs` | Semantic search over workspace documentation indexed in Qdrant. Queries project-specific knowledge base and returns relevant document excerpts |

## Tool loop parity

`complex_llm_node` and `complex_tool_action_node` both resolve tools via `_resolve_complex_tools()` in [`complex.py`](../../src/agent/core/complex.py), honoring `selected_toolboxes`, `web_search_enabled`, and vision web-tool stripping. Context telemetry (`bound_tool_count`, Schemas row) uses the **post-rerank** list actually sent to the model. This keeps bound tools aligned with the `ToolNode` executor on multi-turn tool loops.

## MCP extensions

External MCP servers (stdio) are declared in [`mcp_config.json`](../../mcp_config.json) (see [`mcp_config.json.example`](../../mcp_config.json.example)). At startup, `mcp_manager.initialize()` discovers tools; `merge_mcp_tools()` appends them when toolbox is `all`, `mcp`, or pentest auto-augment.

| Config | Role |
|--------|------|
| `defaults.yaml` → `mcp.*` | Enable, include-on-all, pentest auto-toolbox, HITL prefixes |
| `mcp_config.json` | Server command + env (e.g. Kali SSH for pentest-mcp-server) |

Pentest MCP tools (`pentest_*`) require HITL approval. Guide: [mcp-pentest-kali.md](../guides/mcp-pentest-kali.md).

**Pentest mode:** See [MODES.md](MODES.md) for mode system. See [PENTEST.md](PENTEST.md) for pentest infrastructure documentation.

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Dynamic toolbox selection | Reduces token overhead by ~2000/turn | Router must correctly classify toolbox needs |
| Security proxy gates destructive tools | Safety for file write/edit/delete, notebook execution | HITL latency for approved sensitive calls |
| SSRF protection on downloads | `url_policy.py` blocks private IPs, localhost, cloud metadata on `download_to_workspace` | Only applies to download tool, not all HTTP |
| Always-include `ask_user` | HITL escape hatch on every turn | Minor token overhead |
| Notebook sandbox and timeout | HTTP clients removed from whitelist; prevents exfiltration. 30s timeout prevents infinite loops. | Notebook variable state is lost on timeout reset |

## Testing

Security policy — sensitive tools require approval via `security_proxy` (default: `require_approval`):

| Tool | Risk |
|------|------|
| `write_workspace_file` | File system modification |
| `edit_workspace_file` | File system modification |
| `delete_workspace_file` | Destructive file removal |
| `notebook_run` | Sandboxed code execution (no HTTP clients) |

All other tools auto-approve. Dangerous shell patterns (`rm -rf`, `sudo`, etc.) are blocked by the scope guard regardless of engagement state. `fetch_webpage` output is wrapped in `<web_context>` injection boundary tags.

## Configuration

### Adding a New Tool

1. Create `@tool` function in `src/tools/`
2. Import in `src/agent/tool_sets.py`
3. Add to the appropriate `TOOLBOX_REGISTRY` category (or create a new category)
4. Tool automatically included when that toolbox is selected by the Router
5. Update guidance text in `src/agent/nodes/complex.py`
6. If sensitive, add to `SENSITIVE_TOOLS` in `src/agent/nodes/security_proxy.py`

## Related

- [`docs/API_REFERENCE.md`](API_REFERENCE.md) — REST endpoint reference
- [`docs/architecture/overview.md`](architecture/overview.md) — system architecture

## Last updated

2026-07-10 — Added data_connectors toolbox (ingest_github_repo, ingest_youtube_transcript, ingest_obsidian_vault)
2026-07-09 — Router decomposition (deterministic.py, resolver.py, modes.py); pentest tools section added (56+ tools across 11 categories); @scope_validated decorator applied to pentest tools; pentest memory node added; study tools expanded (flashcard_list, course_delete, study_note_update, quiz_session_delete); model name updated to gemma-4-e2b
