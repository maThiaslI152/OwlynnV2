# Tasks: System Modernization

## Task 1: Migrate to pyproject.toml
- **maps_to:** AC-1
- **files:** `pyproject.toml`, `requirements.txt`
- **action:** Use `uv init` or create `pyproject.toml` manually with the dependencies from `requirements.txt`. Remove `requirements.txt`.
- **verify_steps:**
  - Run `uv pip compile pyproject.toml` (or `uv sync`) to ensure dependencies resolve.

## Task 2: Implement Pre-commit Hooks
- **maps_to:** AC-2
- **files:** `.pre-commit-config.yaml`
- **action:** Create `.pre-commit-config.yaml` using the `ruff-pre-commit` repo targeting `ruff check` and `ruff format`.
- **verify_steps:**
  - Run `pre-commit run --all-files` (or equivalent manual ruff check) to ensure it works.

## Task 3: Setup Playwright
- **maps_to:** AC-3
- **files:** `frontend-v2/playwright.config.ts`, `frontend-v2/package.json`
- **action:** Add `@playwright/test` to devDependencies. Create basic `playwright.config.ts` targeting Electron.
- **verify_steps:**
  - Ensure `npx playwright test` can run without configuration errors.

## Task 4: Write Safemode E2E Test
- **maps_to:** AC-4
- **files:** `frontend-v2/e2e/safemode.spec.ts`
- **action:** Write a test that mounts the app, clicks the safemode toggle, and asserts the UI changes correctly.
- **verify_steps:**
  - Run `npx playwright test e2e/safemode.spec.ts`.

## Task 5: Write Screen-Assist E2E Test
- **maps_to:** AC-5
- **files:** `frontend-v2/e2e/screen-assist.spec.ts`
- **action:** Write a test simulating a user initiating a screen-assist request.
- **verify_steps:**
  - Run `npx playwright test e2e/screen-assist.spec.ts`.

## Task 6: Modernize CSS
- **maps_to:** AC-6
- **files:** `frontend-v2/src/index.css`
- **action:** Add `container-type` to main containers. Apply `view-transition-name` to chat items.
- **verify_steps:**
  - Verify visually (or check that css linting passes).
