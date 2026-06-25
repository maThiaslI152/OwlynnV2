# Contributing to Owlynn

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 18+ (for frontend tests)
- Docker/Podman (for Qdrant, Redis, StirlingPDF; SearXNG optional via compose profile)
- LM Studio with models loaded on port 1234
- Electron (optional — for desktop packaging via `frontend-v2`)

### Backend Setup

```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment config
cp .env.example .env
# Edit .env as needed

# Start infrastructure services
docker-compose up -d

# Run the backend
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend Setup (v2 active)

```bash
cd frontend-v2
npm install
```

The frontend is served by the FastAPI backend at `http://127.0.0.1:8000`. For development, you can also run the Vite dev server separately:

```bash
cd frontend-v2
npm run dev
```

The Vite dev server runs on `http://127.0.0.1:5173` with API/WebSocket proxied to the backend.

## Code Style

### Python

- Follow PEP 8 with a 100-character line limit.
- Use Google-style docstrings for all public functions and classes.
- Type hints on function signatures (use `str | None` over `Optional[str]`).
- Imports: stdlib → third-party → local, separated by blank lines.
- Use `logging` (not `print`) for diagnostic output in production code.

### TypeScript / JavaScript

- Use JSDoc comments for public functions.
- Prefer `const` over `let`; avoid `var`.
- Use `===` for comparisons.

### General

- Keep comments concise and useful — explain *why*, not *what*.
- No commented-out code in commits.
- Meaningful commit messages: `fix(router): handle empty message edge case`.

## Testing

### Backend Tests

```bash
# Run all tests
pytest tests/ -v

# Run only property-based tests
pytest tests/test_crud_properties.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing
```

- Unit tests use `pytest`.
- Property-based tests use `hypothesis` with `@given` decorators.
- All CRUD operations must have both unit and property-based test coverage.
- Tests must clean up after themselves (delete created projects, etc.).

### Frontend Tests

```bash
cd frontend-v2
npx vitest run
```

- Component tests use `@testing-library/react` with `vitest` + `jsdom`.
- Test files go in `frontend-v2/src/components/__tests__/` with `.test.tsx` suffix.

### Before Submitting

```bash
./scripts/ci.sh --quick
```

Or individually:

```bash
pytest -q -m "not network and not benchmark" --tb=short
pytest -q tests/test_verify_report_fixture.py tests/test_websocket_event_contract.py tests/test_frontend_cutover_serving.py --tb=short
cd frontend-v2 && npx vitest run
```

1. All checks above pass
2. New features include tests where behavior changes
3. No lint errors in modified files

## Architecture Notes

- **Agent nodes** are LangGraph callables over `AgentState` — side effects limited to LLM calls, tools, and memory I/O.
- **Memory scoping**: Non-default projects isolate memories via `project:<id>` user IDs in Mem0.
- **Security proxy**: Sensitive tool calls pass through `security_proxy_node` / `plan_review_node` with HITL interrupts.
- **Models**: Unified local model `gemma-4-e2b-heretic-uncensored-mlx` (routing, vision proxy, and memory extraction), cloud complex `deepseek-v4-flash` — see `src/config/defaults.yaml`.

See [`docs/architecture/overview.md`](docs/architecture/overview.md) and [`AGENTS.md`](AGENTS.md).
