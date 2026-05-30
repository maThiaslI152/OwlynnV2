# Coding Style

> **Language-agnostic coding conventions for this project.** Agents **MUST** match existing code in touched files first; if creating new files, apply these conventions.

## General Principles

1. **Consistency over preference.** Match the style of the file you are editing.
2. **Readability over cleverness.** Write code a new team member could understand in one pass.
3. **Explicit over implicit.** Favor clear names and explicit error handling.

## File Layout

- One primary export per file where practical.
- Imports at top: built-ins → third-party → internal modules, alphabetized within groups.
- Exports at bottom (for languages that support it).
- No orphan files in repo root; all source under appropriate directories.

## Naming

| Kind | Convention | Example |
|------|-----------|---------|
| Files | kebab-case | `user-service.ts` |
| Directories | kebab-case | `auth-handlers/` |
| Classes / Types | PascalCase | `UserProfile` |
| Functions / Methods | camelCase | `getUserById()` |
| Variables | camelCase | `userList` |
| Constants | UPPER_SNAKE_CASE | `MAX_PAGE_SIZE` |
| Test files | `*.test.ts`, `*_test.py`, `*_test.go` | `list.test.ts` |

## Imports

- Group and sort: standard library → third-party → internal modules.
- No wildcard imports (e.g., `import * from ...`).
- Prefer named imports over default imports for clarity.

## Error Handling

- Errors must be handled, never silently swallowed.
- Return structured errors with context (not bare strings).
- Log at appropriate level; never log secrets or PII.

## Comments Policy

- Comments explain **why**, not **what**.
- No obvious/narrative comments (e.g., `// Increment the counter`).
- TODO comments must reference a task or issue: `// TODO(slug): description`.
- Keep comments current — stale comments are worse than none.

## Lint and Format Commands

| Stack | Lint | Format |
|-------|------|--------|
| TypeScript/JavaScript | `npm run lint` | `npm run format` |
| Python | `ruff check .` | `ruff format .` |
| Go | `golangci-lint run` | `gofmt -w .` |
| Shell | `shellcheck *.sh` | `shfmt -w .` |

Run lint and format **before marking any task complete**.

## Language-Specific Conventions

### TypeScript / JavaScript
- Prefer `const` over `let`; never use `var`.
- Use `async/await` over raw promises.
- Type everything; avoid `any`.
- Use optional chaining (`?.`) and nullish coalescing (`??`).

### Python
- Follow PEP 8 (ruff enforces this).
- Use type hints on all public functions.
- Prefer dataclasses over raw dicts for structured data.

### Go
- Follow standard Go conventions (`gofmt`).
- Errors as values; no panics in library code.
- Accept interfaces, return structs.

### Shell (Bash)
- `set -euo pipefail` at top of every script.
- Quote all variable expansions.
- Use `[[ ... ]]` for tests, not `[ ... ]`.

## Related

- [`docs/standards/documentation.md`](documentation.md) — doc structure rules
- [`specs/memory/constitution.md`](../../specs/memory/constitution.md) — non-negotiable constraints
- [`.cursor/rules/coding-style.mdc`](../../.cursor/rules/coding-style.mdc) — enforceable rule subset

## Last updated

2026-05-31 — `cursor-sdd-enforcement-harness` initial style guide
