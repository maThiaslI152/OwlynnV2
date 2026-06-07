---
status: active
category: guide
last_updated: 2026-06-07
owner: ai-agent
---

# Dev Startup Guide — Getting Owlynn Running

> **Purpose:** Authoritative startup reference for any developer or LLM agent picking up this project. Covers every prerequisite and step needed to go from `git clone` to a running app at `http://127.0.0.1:5173`. Safe Mode and Screen Assist require Electron IPC — unavailable in raw browser mode.

This is the first document an LLM agent should read when asked "how do I start this app?" — it supersedes codebase scanning. Start here, then follow the numbered steps.

## Prerequisites

Install these before anything else. All commands are for **macOS** (the primary dev platform).

| Component | Minimum Version | Install Command | Why |
|-----------|----------------|-----------------|-----|
| Python | ≥3.11 | `brew install python@3.12` | Backend runtime |
| Node.js | ≥20 | `brew install node` | Frontend build/dev |
| Podman or Docker | Podman 5+ or Docker 25+ | `brew install podman` (or Docker Desktop) | Qdrant + Redis containers |
| LM Studio | latest | Download from [lmstudio.ai](https://lmstudio.ai) | Local LLM inference |

Verify with:

```bash
python3 --version   # ≥3.11
node --version      # ≥20
podman --version    # or: docker --version
```

## Quick Reference

```
http://127.0.0.1:5173           # Frontend (Vite dev server)
http://127.0.0.1:8000           # Backend API (FastAPI)
http://127.0.0.1:1234           # LM Studio (LLM inference)
http://127.0.0.1:6333           # Qdrant (vector DB)
http://127.0.0.1:6379           # Redis (session persistence)
```

## Step 1: Environment Configuration (.env + .env.local)

Copy the templates and fill in the values:

```bash
cp .env.example .env
cp .env.local.example .env.local   # optional — recommended for DEEPSEEK_API_KEY only
```

**Secrets workflow:** Keep general config in `.env`. Put API keys and other secrets in `.env.local` (gitignored). `start.sh` loads `.env` first, then `.env.local` — local values win.

### Centralized Configuration (New — June 2026)

All project settings are in **`src/config/defaults.yaml`** — the single source of truth. Override priority (lowest → highest):

```
defaults.yaml  →  environment variables  →  user_profile.json
```

To swap a model, change 1-2 lines in `defaults.yaml`. No code changes needed.

**Key config sections:**
| Section | What it controls |
|---------|-----------------|
| `models.small` | Router/model for simple tasks (name, base_url, temp, max_tokens, context_window) |
| `models.medium` | Complex local task model (Qwen 9B) |
| `models.cloud` | DeepSeek V4 API (`deepseek-v4-flash` / `deepseek-v4-pro`) |
| `cloud` | Thinking mode, reasoning effort, vision cache TTL |
| `routing` | Confidence thresholds, budget tiers, keyword bypasses |
| `memory` | Max facts, cache TTL, decay constants |
| `web_search` | Search backend timeouts, user-agents |
| `summarization` | Threshold ratio, context windows |
| `complex` | Safety margins, cutoff retries |

**Config validation** runs at startup. Missing paths or missing YAML sections produce warnings in the backend log. Run manually:
```bash
python3 -c "from src.config.config_loader import validate_config; print(validate_config())"
```

**All env-overridable variables:**
| Env Var | Overrides | YAML Default |
|---------|-----------|-------------|
| `HOST` | `server.host` | `127.0.0.1` |
| `PORT` | `server.port` | `8000` |
| `SMALL_LLM_BASE_URL` | `models.small.base_url` | `http://127.0.0.1:1234/v1` |
| `MEDIUM_LLM_BASE_URL` | `models.medium.base_url` | same |
| `CLOUD_LLM_BASE_URL` | `models.cloud.base_url` | `https://api.deepseek.com/v1` |
| `SMALL_LLM_MODEL_NAME` | `models.small.model_name` | `minicpm5-1b` |
| `MEDIUM_LLM_MODEL_NAME` | `models.medium.model_name` | `qwen3.5-9b-...@q6_k` |
| `CLOUD_LLM_MODEL_NAME` | `models.cloud.model_name` | `deepseek-v4-flash` |
| `DEEPSEEK_API_KEY` | env (or `.env.local`) | — |
| `QDRANT_HOST` / `QDRANT_PORT` | `external_services.qdrant.*` | `localhost:6333` |
| `REDIS_URL` | `external_services.redis.url` | `redis://localhost:6379` |
| `SEARXNG_URL` | `external_services.searxng.url` | `""` |
| `VOICE_WAKE_WORD` | `server.voice.wake_word` | `Athena` |
| `VOICE_AUTO_TTS` | `server.voice.auto_tts` | `true` |
| `WEB_RAG_*` (7 vars) | `web_rag.*` | see defaults.yaml |
| `WEB_SEARCH_*` (3 vars) | `web_search.*` | see defaults.yaml |

### Mandatory variables to configure

| Variable | What to set | Where to get the value |
|----------|-------------|----------------------|
| `SMALL_LLM_BASE_URL` | `http://127.0.0.1:1234/v1` | LM Studio default |
| `MEDIUM_LLM_BASE_URL` | `http://127.0.0.1:1234/v1` | Same LM Studio instance |
| `SMALL_LLM_MODEL_NAME` | Exact model name | LM Studio → Models tab → loaded model name |
| `MEDIUM_LLM_MODEL_NAME` | Exact model name | LM Studio → Models tab → loaded model name |
| `HOST` | `127.0.0.1` | Default (no change needed) |
| `PORT` | `8000` | Default (no change needed) |

### Optional variables

| Variable | Purpose |
|----------|---------|
| `DEEPSEEK_API_KEY` | Cloud route (`complex-cloud`); prefer `.env.local` over `.env` |
| `CLOUD_LLM_MODEL_NAME` | `deepseek-v4-flash` or `deepseek-v4-pro` (only with API key) |
| `OPTIMIZE_FOR_M4` | Set to `true` on Mac M4 Air for shorter timeouts / memory limits (optional; CI works without it) |
| `SEARXNG_URL` | Self-hosted search engine for web search (optional) |
| `REDIS_URL` | Default `redis://localhost:6379` — no change needed |
| `DOCLING_ARTIFACTS_PATH` | `.models/docling/` — auto-set, no change needed |

## Step 2: Containers (Qdrant + Redis)

The launcher script (`start.sh`) tries three backends in order: `podman compose` → `podman-compose` → `docker compose`. Any of these work.

```bash
# Start containers (choose one)
podman compose up -d     # preferred (Podman users)
docker compose up -d     # Docker users

# Verify they're running
podman ps --format '{{.Names}}' | grep owlynn
# Expected: owlynn_qdrant, owlynn_redis
```

If you don't have either installed, `start.sh` will fail with a clear error. Install Podman (`brew install podman`) or Docker Desktop, then retry.

## Step 3: LM Studio (Local LLM)

See [`docs/guides/lm_studio.md`](lm_studio.md) for full model setup instructions. Quick checklist:

1. Open LM Studio
2. Download and load models:
   - Router: `minicpm5-1b` (small slot)
   - Worker: `qwen3.5-9b-uncensored-hauhaucs-aggressive@q6_k` (medium slot)
   - **Vision:** also load `mmproj-Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-BF16.gguf` for chat image attachments
   - **RAG only:** `text-embedding-nomic-embed-text-v1.5-embedding` (not used for chat images)
3. Start the local server (button in the top bar) — listens on port `1234`
4. Verify: `curl -s http://127.0.0.1:1234/v1/models | python3 -m json.tool`
5. Match the model names in `.env` / `defaults.yaml` to exactly what LM Studio reports

The launcher will pause and prompt you if LM Studio isn't reachable — you can start it then and press Enter.

## Step 4: Python Backend

```bash
# Create venv (first time only)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify imports work
python3 -c "import src.api.server; print('OK')"
```

Key packages installed: `langgraph`, `fastapi`, `uvicorn`, `mem0ai`, `playwright`, `watchdog`, `langchain-openai`.

## Step 5: Frontend

```bash
cd frontend-v2

# Install dependencies (first time only)
npm install

# Quick build check
npx tsc --noEmit
```

The frontend is a React 19 + Vite app. Running `npm run dev` uses Vite's dev server to launch the Electron Desktop app directly.

## Step 6: Launch Everything

```bash
./start.sh
```

What `start.sh` does, in order:

1. **Env** — sources `.env` then `.env.local` if present
2. **Containers** — brings up Qdrant + Redis via podman/docker compose (skips if already running)
3. **LM Studio** — checks port `1234`, prompts you to start it if not responding
4. **Backend** — `uvicorn src.api.server:app --port 8000` with auto-reload
5. **Frontend** — `cd frontend-v2 && npx vite --port 5173`

The script opens `http://127.0.0.1:5173` in your browser. Press `Ctrl+C` to stop everything — the cleanup trap kills all background processes.

### Running components individually

If you prefer to start components separately:

```bash
# Backend only
source .venv/bin/activate
uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload

# Frontend only
cd frontend-v2 && npx vite --host 127.0.0.1 --port 5173

# CLI query (requires backend running)
python3 src/cli.py status
python3 src/cli.py stream "Hello, what can you do?"
```

## Troubleshooting

| Mode | Backend | Frontend | Electron | Best For |
|------|---------|----------|----------|----------|
| `./start.sh` | Yes | Vite HMR | No | Daily browser use |
| Browser (manual) | Yes | Vite HMR | No | Dev, hot reload |
| CLI | Yes | No | No | Scripting, API testing |

| Symptom | Most Likely Cause | Fix |
|---------|------------------|-----|
| `start.sh`: "ERROR: .venv not found" | Python venv not created | Run `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` |
| `start.sh`: "ERROR: Could not start containers" | No Podman/Docker installed | Install Podman (`brew install podman`) or Docker Desktop |
| LM Studio "Not responding on port 1234" | LM Studio server not started | Open LM Studio, click "Start Server" in the top bar, then press Enter in terminal |
| Backend crashes with "No module named 'src'" | PYTHONPATH not set | `start.sh` sets it automatically. If running manually: `export PYTHONPATH="$(pwd):$PYTHONPATH"` |
| Frontend: "command not found: vite" | `npm install` not run | `cd frontend-v2 && npm install` |
| Backend starts but LLM calls fail | Model name mismatch | Check `.env` model names match exactly what LM Studio reports at `http://127.0.0.1:1234/v1/models` |
| Port 8000/5173 already in use | Stale process from previous run | `lsof -ti:8000 | xargs kill -9` and `lsof -ti:5173 | xargs kill -9`, then retry |
| Redis unavailable warning | Redis container not running | `podman compose up -d` or ignore — falls back to in-memory `MemorySaver` automatically |
| Frontend builds but blank page | Vite dev server not proxying API | Ensure backend is running on port 8000; Vite proxies `/api` and `/v1` to it |
| `npm run build` fails | TypeScript errors | Run `cd frontend-v2 && npx tsc --noEmit` to see errors |

## Architecture at a Glance

```
Browser (http://127.0.0.1:5173)
  │
  ├─► Vite Dev Server (port 5173)
  │     └─► React 19 + Zustand + WebSocket client
  │
  ├─► FastAPI Backend (port 8000)
  │     ├─► LangGraph Agent (router → simple/complex nodes)
  │     ├─► WebSocket handler (streaming responses)
  │     └─► Tool execution (web search, file ops, MCP)
  │
  ├─► LM Studio (port 1234)
  │     └─► Local LLM inference (small/medium models)
  │
  ├─► Qdrant (port 6333)
  │     └─► Long-term memory (mem0 embeddings)
  │
  └─► Redis (port 6379)
        └─► LangGraph checkpointing / session persistence
```

## Electron Desktop App

The application is distributed natively via Electron.
During development, simply running `npm run dev` inside `frontend-v2` will launch the app in an Electron window with HMR.

To build the macOS `.app` and `.dmg`:

```bash
cd frontend-v2 && npm run build
```

The output will be placed in `frontend-v2/dist/`.

## Related

- [`start.sh`](../../start.sh) — the single launcher script
- [`.env.example`](../../.env.example) — general environment variables
- [`.env.local.example`](../../.env.local.example) — gitignored secrets template (`DEEPSEEK_API_KEY`)
- [`docs/guides/lm_studio.md`](lm_studio.md) — LM Studio model setup
- [`docs/guides/quickstart.md`](quickstart.md) — chat UX features (highlighting, tool cards, mobile)
- [`AGENTS.md`](../../AGENTS.md) — SDD workflow for Cursor agents
- [`docs/README.md`](../README.md) — full project documentation map
