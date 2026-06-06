---
status: active
category: guide
last_updated: 2026-06-06
owner: ai-agent
---

# System Modernization & CI Testing Guide

This document outlines the system modernization upgrades implemented in June 2026. The primary goal of these upgrades was to move the project to the latest standard tooling for dependency management, code quality enforcement, and End-to-End (E2E) UI testing.

## 1. Backend Dependency Migration (`uv` & `pyproject.toml`)

Previously, Owlynn used a standard `requirements.txt` file for its Python backend dependencies. To improve installation speed, ensure deterministic builds, and adopt modern Python packaging standards, the project has migrated to `pyproject.toml` managed by `uv`.

### Why `uv`?
`uv` is a Rust-based Python package installer and resolver that is drastically faster than `pip`. It provides robust virtual environment management and generates strict lockfiles (`uv.lock`).

### How to manage dependencies now:
- **Install dependencies:** Run `uv sync` (this replaces `pip install -r requirements.txt`).
- **Add a new package:** Run `uv add <package_name>`.
- **Update lockfile:** Run `uv lock`.

The `pyproject.toml` file now acts as the single source of truth for all project metadata, dependencies, and tool configurations (like `pytest` and `ruff`).

---

## 2. Pre-Commit Hooks for Code Quality

To prevent formatting regressions from reaching the Continuous Integration (CI) pipeline, we have implemented local Git hooks using `pre-commit`.

### How it works:
A `.pre-commit-config.yaml` file exists at the root of the project. It uses the `ruff-pre-commit` repository to automatically run two checks whenever you type `git commit`:
1. `ruff check --fix`: Automatically finds and fixes linting errors.
2. `ruff format`: Enforces the standard 88-character line length and standardizes code style.

### Developer Setup:
If you are developing locally, ensure you have installed the hooks:
```bash
uv tool install pre-commit
pre-commit install
```
Now, Git will refuse to commit badly formatted code, automatically fixing it for you.

---

## 3. Frontend End-to-End (E2E) Testing

While the project already had component-level testing via `vitest`, there was no automated way to test the compiled Electron application. We introduced `@playwright/test` to solve this.

### Configuration
Playwright is configured in `frontend-v2/playwright.config.ts`. It is configured to launch the local Electron application and simulate actual user interactions.

### Current Test Workflows
We have implemented coverage for critical features:
1. **Safemode Toggle (`e2e/safemode.spec.ts`):** Validates that clicking the safemode toggle on the sidebar correctly updates the UI state and displays the protective banner.
2. **Screen-Assist Overlay (`e2e/screen-assist.spec.ts`):** Tests the invocation of the Screen-Assist tool, ensuring that the overlay successfully mounts and can be canceled correctly.

### Running the Tests
To run the Playwright test suite:
```bash
cd frontend-v2
npx playwright test
```

---

## 4. Modern CSS Additions

To reduce reliance on heavy Javascript animation libraries and complex media queries, `index.css` has been upgraded with native browser features:

- **Container Queries:** `.sidebar` and `.content-area` now use `container-type: inline-size`. This allows child elements to adapt to the width of their specific container rather than the entire viewport, making components highly reusable.
- **View Transitions:** Added `view-transition-name` support for chat elements, allowing native DOM morphing animations when swapping between views.
