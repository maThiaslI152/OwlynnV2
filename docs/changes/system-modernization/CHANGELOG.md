# System Modernization Changelog

## Task 1: Migrate to pyproject.toml
- Removed legacy `requirements.txt`.
- Created standard `pyproject.toml` containing all core dependencies.
- Generated deterministic lockfile `uv.lock` using the modern `uv` package manager.

## Task 2: Implement Pre-commit Hooks
- Created `.pre-commit-config.yaml` using the `ruff-pre-commit` repo.
- Enforces `ruff check` and `ruff format` before every commit.

## Task 3: Setup Playwright
- Installed `@playwright/test`.
- Configured `playwright.config.ts` for end-to-end testing of the Electron frontend.

## Task 4: Write Safemode E2E Test
- Created `frontend-v2/e2e/safemode.spec.ts`.
- Validates the Safemode toggle state and UI updates on the Sidebar.

## Task 5: Write Screen-Assist E2E Test
- Created `frontend-v2/e2e/screen-assist.spec.ts`.
- Validates the screen-assist initiation flow and overlay UI.

## Task 6: Modernize CSS
- Added `@container` inline-size queries for layout.
- Configured native CSS View Transitions for chat animations.
