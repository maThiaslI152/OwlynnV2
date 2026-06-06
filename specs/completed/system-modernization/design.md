# Design: System Modernization

## Architecture Changes

### 1. Python Package Management (`uv` and `pyproject.toml`)
We will use `uv` to manage the backend dependencies. We will generate a `pyproject.toml` that lists all the dependencies previously defined in `requirements.txt` (like `langgraph`, `fastapi`, `crawl4ai`, `mem0ai[nlp]`). The backend will adopt the modern standardized format, creating an environment that is significantly faster to install and resolve dependencies. 

### 2. Pre-Commit Hooks
We will introduce a `.pre-commit-config.yaml` file at the root of the project. It will use the official `ruff-pre-commit` repository to run:
- `ruff check` (linting)
- `ruff format` (formatting)

This hook will automatically validate staged files on `git commit`. 

### 3. Frontend End-to-End Testing (Playwright)
We will introduce `@playwright/test` for Electron automation. 
- **Setup:** A new `playwright.config.ts` will be created in `frontend-v2/` to target the Vite dev server or Electron build.
- **Test Files:** We will create two specific test files inside `frontend-v2/e2e/`:
  - `safemode.spec.ts`: Tests the interaction with the Safemode toggle on the sidebar, verifying that clicking it properly updates the UI state (and potentially restricts tools).
  - `screen-assist.spec.ts`: Tests the Screen-Assist feature workflow, validating that the UI prompts and handles screen-related context correctly.

### 4. Modern CSS Implementation
We will update `frontend-v2/src/index.css`.
- **Container Queries:** We will set `container-type: inline-size` on the primary layout containers (e.g., the `.sidebar` or main `.content` area). Child elements will adapt their layouts using `@container (min-width: 300px)` rather than global `@media` queries.
- **View Transitions:** We will apply `view-transition-name` to core elements like the chat thread container to allow native, smooth DOM transitions without extra Javascript libraries.

## Data Flow / Interface
- **Python Setup:** No application runtime behavior changes. The only change is in how dependencies are fetched.
- **Pre-commit:** Enforced locally by `git`.
- **Playwright:** The tests run independently of Vitest and only target the compiled UI layer.

## Verification
- Successful creation of `uv.lock`.
- `.pre-commit-config.yaml` successfully formats and passes all current python files.
- `npx playwright test` correctly executes and passes the two new E2E tests for safemode and screen-assist.
- The UI properly uses container queries when resizing the app window.
