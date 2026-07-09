# Eco-Mode Implementation

## 2026-07-09 — Eco-Mode Background Throttling and Intelligent Routing

**What**
Implemented a comprehensive "Eco-Mode" that activates when the Mac is running on battery power. This mode prevents heavy background operations and local LLM execution from draining the battery.
- `pmset -g batt` is monitored every 10 seconds to broadcast `eco_mode_changed` events via WebSocket.
- Background RAG processing (Redis consumer in `worker.py`) suspends and queues tasks.
- Background file extraction (`file_processor.py`) is skipped, except for explicit file uploads via the frontend UI.
- Local LLM routing automatically overrides to `complex-cloud` (Gemini Flash) to avoid heavy local CPU/GPU usage.
- The frontend UI displays warnings before launching Kali VM in Pentest mode when on battery, and updates a Zustand store (`modesSlice`) with `isEcoMode`.

**Why**
Local models like Qwen3 and Gemma 4 12B, along with background extraction tasks, consume significant power and cause thermal throttling when disconnected from a power adapter. This ensures Owlynn remains performant and battery-friendly.

**Files**
- `src/api/power_monitor.py` (New)
- `src/api/server.py`
- `src/agent/routing/router.py`
- `src/memory/extraction/worker.py`
- `src/api/file_processor.py`
- `src/api/routes/files.py`
- `src/api/ws/schemas.py`
- `frontend-v2/src/state/slices/modesSlice.ts`
- `frontend-v2/src/App.tsx`
- `frontend-v2/src/components/ModeSwitchModal.tsx`
