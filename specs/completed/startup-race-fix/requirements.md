# Requirements: Startup Race Fix & Settings Consolidation

> **Purpose:** Define requirements to resolve the LM Studio model swap startup race condition and fix the missing default settings fields regression in the unified settings endpoint.
> **Slug:** `startup-race-fix`

## User Stories

| ID | As a ... | I want to ... | So that ... |
|----|----------|---------------|-------------|
| US-1 | System Operator | Have the server block readiness until LLMs are preloaded and warmed up | Cold-start requests (like T1.1) do not fail immediately with 0-second model-unavailable errors. |
| US-2 | Developer | Have the server start successfully even if warmup fails/times out | External service issues (e.g., LM Studio offline) do not completely block server startup in local mode. |
| US-3 | Frontend UI Client | Receive default LLM configuration fields in `/api/unified-settings` | The settings panels display current active settings rather than empty/missing fields when no user overrides exist. |

## Acceptance Criteria (EARS format)

| ID | Criterion |
|----|-----------|
| AC-1 | When the server starts up, the lifespan setup block **shall await** the completion of LLM preloading and warmup before resolving, preventing connections until models are ready. |
| AC-2 | When LLM preloading or warmup fails or encounters a timeout, the system **shall log a warning and complete lifespan setup** to allow fallback operation. |
| AC-3 | When `/api/unified-settings` is requested, the endpoint **shall populate missing LLM configuration fields** (`small_llm_base_url`, `small_llm_model_name`, `llm_base_url`, `llm_model_name`, `medium_models`, `cloud_llm_base_url`, `cloud_llm_model_name`) using defaults resolved from the centralized config loader. |

## Edge Cases and Error States

- **LM Studio Offline:** If LM Studio is not running, both small and medium warmups will time out or raise connection errors. The server must still boot successfully.
- **Partially Configured Profiles:** If some fields are overridden in `user_profile.json` but others are not, the unified settings payload must merge both values correctly without duplicates.

## Out of Scope

- Implementing the custom coherence checks (R5) or refactoring `server.py` into separate route files (D1).

## References

- `docs/STATUS.md` — R1 One-turn lag, model preloading findings
- `docs/evaluations/owlynn-conversation-2026-06-04-v7-final.md` — Startup race findings
- Centralized config documentation

## Approval

- `requirements-review` AskQuestion: approved (2026-06-04)
