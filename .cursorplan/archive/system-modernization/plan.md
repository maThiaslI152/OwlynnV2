# SDD Plan: System Modernization

## Requirements
- **AC-1:** The backend is fully migrated from `requirements.txt` to `pyproject.toml` utilizing `uv` for package management.
- **AC-2:** A `.pre-commit-config.yaml` is added to enforce `ruff check` and `ruff format` before commits.
- **AC-3:** `@playwright/test` is installed and configured in the `frontend-v2/` directory for Electron E2E testing.
- **AC-4:** An E2E test is implemented for the **Safemode** toggles and behaviors on the Sidebar.
- **AC-5:** An E2E test is implemented for the **Screen-Assist** feature workflows.
- **AC-6:** Legacy media queries in `index.css` are upgraded to modern Container Queries (`@container`), and basic View Transitions are introduced for state changes.

## Design
1. **Python Package Management:** Use `uv` to manage the backend dependencies, generating a `pyproject.toml` and lockfile.
2. **Pre-Commit Hooks:** Introduce a `.pre-commit-config.yaml` to run `ruff check` and `ruff format`.
3. **Frontend E2E Testing (Playwright):** Create `playwright.config.ts`, `e2e/safemode.spec.ts`, and `e2e/screen-assist.spec.ts`.
4. **Modern CSS Implementation:** Update `frontend-v2/src/index.css` to use `container-type: inline-size` and `view-transition-name`.

## Tasks
1. Initialize `pyproject.toml` and migrate `requirements.txt`
2. Implement Pre-commit Hooks
3. Setup Playwright
4. Write Safemode E2E Test
5. Write Screen-Assist E2E Test
6. Modernize CSS
