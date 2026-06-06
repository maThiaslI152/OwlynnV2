# Requirements: System Modernization

## Goal
Modernize the Owlynn tech stack and enforce rigorous quality gates to prevent CI regressions and ensure robust UI testing.

## Context
Following an architectural audit, the backend dependency management was found to use legacy `requirements.txt` instead of modern `pyproject.toml` standards. Additionally, the project lacks pre-commit formatting enforcement and end-to-end (E2E) testing for the Electron UI. The user requested to migrate to `pyproject.toml` using `uv` and to implement Playwright tests for specific workflows (Safemode and Screen-Assist).

## Acceptance Criteria (AC)

- **AC-1:** The backend is fully migrated from `requirements.txt` to `pyproject.toml` utilizing `uv` for package management.
- **AC-2:** A `.pre-commit-config.yaml` is added to enforce `ruff check` and `ruff format` before commits.
- **AC-3:** `@playwright/test` is installed and configured in the `frontend-v2/` directory for Electron E2E testing.
- **AC-4:** An E2E test is implemented for the **Safemode** toggles and behaviors on the Sidebar.
- **AC-5:** An E2E test is implemented for the **Screen-Assist** feature workflows.
- **AC-6:** Legacy media queries in `index.css` are upgraded to modern Container Queries (`@container`), and basic View Transitions are introduced for state changes.

## Out of Scope
- Backend logic changes outside of dependency tooling.
- Rewriting component-level tests (`vitest` / `@testing-library/react`).
