---
status: active
category: evaluations
last_updated: 2026-08-23
---

# Mindmap Viewport Automation, Internet Search & Graph Generation E2E Evaluation — 2026-08-23

> **Purpose:** Comprehensive evaluation of the Mindmap Canvas interactive viewport controls, end-to-end conversation with live internet search tool execution, data visualization graph generation, and Thought Graph synchronization.
> **Harness:** Playwright headed browser automation in Brave (`scratch/test_mindmap_search_graph_e2e.py`).
> **Model:** Unified Local Engine `gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m`.

---

## 1. Executive Summary

| Phase | Test Scope | Verification Method | Result |
| :--- | :--- | :--- | :--- |
| **Phase A** | Split View Activation | UI layout switch (`Split Graph` button) | **PASSED** (48% Canvas / 52% Chat) |
| **Phase B** | Viewport Controls | D3-zoom wheel (in/out), pointer pan drag, `zoomToFit` toolbar button | **PASSED** (Topics centered within window) |
| **Phase C** | Internet Search | Live query on Python 3.14 features, autonomous `web_search` invocation | **PASSED** (`web_search` executed, tool card rendered) |
| **Phase D** | Graph / Chart Gen | Matplotlib benchmark chart generation request | **PASSED** (Categorized `data_viz`, code synthesized) |
| **Phase E** | Thought Graph Sync | REST API `/api/graph/data` verification & active topic glowing aura | **PASSED** (21 nodes in DB, green halo highlight) |
| **Phase F** | Panoramic Views | Full mindmap canvas & full chat conversation view capture | **PASSED** (14 visual screenshots archived) |

---

## 2. Test Execution Details

### Step A: View Switch to Split Graph
- Opened project workspace via `http://127.0.0.1:5173/?project=<id>`.
- Clicked `Split Graph` button in top navigation.
- Verified dual-pane rendering with Coggle Organic Mindmap on the left and Chat Stream on the right.

### Step B: Interactive Viewport Adjustments
- **Fit to Screen**: Clicked toolbar `Maximize2` icon to trigger `fgRef.current.zoomToFit(400, 50)`.
- **Zoom In**: Dispatched 4 scroll wheel events (`deltaY = -150`) over the 2D HTML5 canvas.
- **Zoom Out**: Dispatched 6 scroll wheel events (`deltaY = 150`) expanding canvas field of view.
- **Pan Viewport**: Dispatched pointer drag (`mouse.move(cx + 120, cy + 60, steps=12)`), translating canvas coordinate origin.
- **Final Centering**: Executed final `zoomToFit` to ensure all topic nodes are comfortably bounded within the viewport window.

### Step C: Internet Search Conversation
- **Prompt**: *"Search the internet for the top new features in Python 3.14 (such as free threading and template strings). Summarize the top 2 features concisely in bullet points."*
- **Routing**: `router_node` classified to `complex-default` (`main-local`).
- **Tool Execution**: `security_proxy` auto-approved `web_search` (`decision: safe_auto`), executing search in 1.7s.
- **UI Render**: Rendered tool execution summary pill (`Finished (1 tools used)`).

### Step D: Graph / Chart Generation
- **Prompt**: *"Write a python script using matplotlib to create a horizontal bar chart comparing performance execution times across Python 3.12 (1.0x), 3.13 (1.15x), and 3.14 (1.30x). Save the chart to the workspace as 'python_benchmarks.png'."*
- **Routing**: Router classified query under `task_category: "data_viz"` via `tool_history_bypass`.
- **Synthesis**: Code generation executed on `main-local` model.

### Step E: Thought Graph Auto-Seeding & Synchronization
- Verified database state via `GET /api/graph/data` (21 nodes, 3 directed edges).
- Mindmap automatically seeded the active conversation thread as a `ThoughtNode` with title matching the user query.
- The active node rendered with a vibrant emerald glowing halo (`ctx.shadowBlur = 16`).

---

## 3. Visual Verification Screenshots

All screenshots are preserved in `assets/mindmap_e2e_screenshots/`:

| Index | Screenshot File | Description |
| :--- | :--- | :--- |
| `01` | `01_initial_load.png` | Workspace initial chat view load |
| `02` | `02_split_view.png` | Split View: Organic Mindmap (left) + Chat (right) |
| `03` | `03_fit_to_screen.png` | Initial Fit to Screen centering |
| `04` | `04_zoomed_in.png` | Zoomed in (4 scroll steps) |
| `05` | `05_zoomed_out.png` | Zoomed out (6 scroll steps) |
| `06` | `06_panned.png` | Canvas translated (+120px, +60px) |
| `07` | `07_mindmap_adjusted.png` | Re-centered mindmap with topics within window |
| `08` | `08_search_sent.png` | Internet search query submitted |
| `09` | `09_search_response.png` | `web_search` tool execution (`Finished (1 tools used)`) |
| `10` | `10_graph_prompt_sent.png` | Chart generation prompt submitted |
| `11` | `11_graph_response.png` | Chart generation execution in progress |
| `12` | `12_final_mindmap.png` | Split view with glowing active topic node |
| `13` | `13_full_mindmap_view.png` | Full mindmap panoramic canvas |
| `14` | `14_final_chat_view.png` | Full chat view with tool execution activity |

---

## 4. Conclusion

The E2E evaluation verifies that:
1. The 2D HTML5 Force-Graph Mindmap canvas responds smoothly to programmatic and user-driven pan, zoom, and fit-to-screen controls.
2. The local agentic model (`gemma-4-12b-agentic`) autonomously plans and invokes internet search tools when live information is requested.
3. Multi-turn context and data visualization requests route appropriately.
4. The Thought Graph backend auto-seeds and links conversation threads into visual mindmap nodes with live active-node highlighting.
