---
status: active
category: guide
last_updated: 2026-05-31
owner: human
---

# Audit Export + Verify Runbook

> **Purpose:** Operator runbook for exporting and verifying tool-execution audit artifacts.

This runbook defines the operator workflow for producing and validating tool-execution audit artifacts from `frontend-v2`.

## Scope

- Export tool execution audit bundles from inspector.
- Validate bundle integrity (hash chain, root hash, digest, optional signature).
- Attach verify report to incident/audit tickets.

## Prerequisites

- `frontend-v2` running with recent tool execution history.
- Inspector panel visible.
- For signed bundle verification: signing secret available to authorized operator.

## Procedure

1. Open Inspector -> `Tool Execution`.
2. Choose filter scope (`all`, `risky`, `error`) based on incident scope.
3. (Optional) set signing inputs:
   - `signing key id`
   - `signing secret`
4. Click `export-jsonl`.
   - Output artifacts:
     - `owlynn-tool-audit-<ts>.jsonl`
     - `owlynn-tool-audit-<ts>.jsonl.manifest.json`
5. Verify in-app:
   - choose manifest + JSONL files,
   - if manifest is signed (`hmac-sha256`), provide verify secret,
   - click `verify-bundle`.
6. Export report:
   - click `export-verify-report`,
   - attach resulting `owlynn-verify-report-<ts>.json` to ticket.

## Expected outcomes

- Pass path:
  - Operator note: `Verify OK: ...`
  - Verify report status: `pass`
- Fail path:
  - Operator note: `Verify failed: ...`
  - Verify report status: `fail` with step trace context.

## Ticket attachment checklist

- [ ] JSONL bundle attached
- [ ] Manifest sidecar attached
- [ ] Verify report attached
- [ ] Filter scope noted (`all`/`risky`/`error`)
- [ ] For signed bundles: signing key id recorded

## Troubleshooting

- `Hash chain verification failed`:
  - bundle likely modified, truncated, or mismatched with manifest.
- `Manifest root hash mismatch`:
  - wrong manifest for selected JSONL bundle, or bundle tampered.
- `Manifest digest mismatch`:
  - manifest modified after export.
- `Manifest signature mismatch`:
  - wrong verify secret or modified manifest.

## Related

- [`docs/README.md`](README.md) — project documentation map
- [`docs/AI_AGENT_INDEX.md`](AI_AGENT_INDEX.md) — navigation index

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter, purpose blockquote
