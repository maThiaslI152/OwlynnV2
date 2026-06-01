# Verification — Project-Level Test Contract

> **How to test this repository.** Every agent **MUST** read this before running any `verify_steps`.

## Default Test Commands

| Stack | Command | Notes |
|-------|---------|-------|
| Node.js / TypeScript | `npm test` | Runs all tests |
| Python | `pytest` | Runs all tests |
| Go | `go test ./...` | Runs all packages |
| Rust | `cargo test` | Runs all tests |
| Generic shell | `./test.sh` | If present in project root |

## Running a Single Test

| Stack | Command |
|-------|---------|
| Node.js / TypeScript | `npm test -- <path/to/test>` |
| Python | `pytest <path/to/test_file.py>` |
| Go | `go test ./<package>/...` |
| Rust | `cargo test <test_name>` |

## Coverage Expectations

- Target: determined per project. Check `package.json`, `Makefile`, or CI config for thresholds.
- Minimum: no uncovered critical paths.

## CI Command to Mirror Locally

```bash
# Check CI configuration for the canonical command. Examples:
npm run ci        # Node
pytest --strict   # Python
go test -race ./...  # Go
```

## What Counts as "Pass"

- Exit code 0
- No skipped critical tests (critical tests are marked with `@critical` or equivalent)
- No regressions vs. previous `verify_steps` run
- All commands in the task's `verify_steps` list completed without error

## Agent Verification Protocol

1. Read this file at start of verification phase.
2. For each task's `verify_steps`, run commands in order.
3. Capture output to `state.json.verification.tasks[n].output`.
4. Record pass/fail in `state.json.verification.tasks[n].status`.
5. Do NOT show `task-verify-{n}` popup until all steps for that task are complete.

## Related

- [`specs/memory/constitution.md`](constitution.md) — SDD rules
- [`specs/templates/verification-report.md`](../templates/verification-report.md) — per-change report template
- [`docs/standards/coding-style.md`](../docs/standards/coding-style.md) — lint/format commands

## Last updated

2026-05-31 — `cursor-sdd-enforcement-harness` initial contract
