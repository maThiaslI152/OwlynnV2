import type { CloudUsageState, ContextBreakdown } from '../state/useAppStore'

function asNumber(value: unknown, fallback = 0): number {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

/** Normalize /api/usage or cloud_usage WS payload into store shape. */
export function parseCloudUsagePayload(payload: Record<string, unknown>): CloudUsageState {
  // /api/usage returns token counts in `session` and cost/calls in `cost` (tracker.summary).
  // WS cloud_usage uses a full `session` from the tracker. Merge so refetches keep the chip.
  const sessionPartial = (payload.session ?? {}) as Record<string, unknown>
  const costPartial = (payload.cost ?? {}) as Record<string, unknown>
  const sessionRaw = {
    ...costPartial,
    ...sessionPartial,
    total_calls: costPartial.total_calls ?? sessionPartial.total_calls,
    failed_calls: costPartial.failed_calls ?? sessionPartial.failed_calls,
    estimated_cost_usd:
      costPartial.estimated_cost_usd ?? sessionPartial.estimated_cost_usd,
    elapsed_seconds: costPartial.elapsed_seconds ?? sessionPartial.elapsed_seconds,
    cache_hit_ratio: costPartial.cache_hit_ratio ?? sessionPartial.cache_hit_ratio,
    reasoning_tokens: costPartial.reasoning_tokens ?? sessionPartial.reasoning_tokens,
    last_turn:
      sessionPartial.last_turn ?? costPartial.last_turn ?? payload.last_turn ?? null,
  } as Record<string, unknown>
  const budgetRaw = (payload.budget ?? {}) as Record<string, unknown>
  const lastTurnRaw = (sessionRaw.last_turn ?? payload.last_turn ?? null) as
    | Record<string, unknown>
    | null

  const lastTurn = lastTurnRaw
    ? {
        prompt_tokens: asNumber(lastTurnRaw.prompt_tokens),
        completion_tokens: asNumber(lastTurnRaw.completion_tokens),
        prompt_cache_hit_tokens: asNumber(lastTurnRaw.prompt_cache_hit_tokens),
        prompt_cache_miss_tokens: asNumber(lastTurnRaw.prompt_cache_miss_tokens),
        reasoning_tokens: asNumber(lastTurnRaw.reasoning_tokens),
        model_tier: String(lastTurnRaw.model_tier || ''),
        model_name: String(lastTurnRaw.model_name || ''),
        estimated_cost_usd: asNumber(lastTurnRaw.estimated_cost_usd),
        cache_hit_ratio: asNumber(lastTurnRaw.cache_hit_ratio),
      }
    : null

  return {
    session: {
      prompt_tokens: asNumber(sessionRaw.prompt_tokens),
      completion_tokens: asNumber(sessionRaw.completion_tokens),
      prompt_cache_hit_tokens: asNumber(sessionRaw.prompt_cache_hit_tokens),
      prompt_cache_miss_tokens: asNumber(sessionRaw.prompt_cache_miss_tokens),
      reasoning_tokens: asNumber(sessionRaw.reasoning_tokens),
      total_tokens: asNumber(sessionRaw.total_tokens),
      cache_hit_ratio: asNumber(sessionRaw.cache_hit_ratio),
      total_calls: asNumber(sessionRaw.total_calls),
      failed_calls: asNumber(sessionRaw.failed_calls),
      estimated_cost_usd: asNumber(sessionRaw.estimated_cost_usd),
      elapsed_seconds: asNumber(sessionRaw.elapsed_seconds),
      last_turn: lastTurn,
    },
    budget: {
      daily_token_limit: asNumber(budgetRaw.daily_token_limit),
      used_tokens: asNumber(budgetRaw.used_tokens),
      remaining_tokens:
        budgetRaw.remaining_tokens == null
          ? null
          : asNumber(budgetRaw.remaining_tokens),
      used_pct: asNumber(budgetRaw.used_pct),
    },
    lastTurn,
  }
}

/** Parse context_breakdown from model_info token_usage or api payload. */
export function parseContextBreakdown(raw: unknown): ContextBreakdown | null {
  if (!raw || typeof raw !== 'object') return null
  const bd = raw as Record<string, unknown>
  const categories = (bd.categories ?? {}) as Record<string, unknown>
  const categoryPct = (bd.category_pct ?? {}) as Record<string, unknown>
  const maxContext = asNumber(bd.max_context)
  if (maxContext <= 0) return null
  return {
    max_context: maxContext,
    categories: {
      system: asNumber(categories.system),
      conversation: asNumber(categories.conversation),
      tools: asNumber(categories.tools),
      schemas: asNumber(categories.schemas),
      output: asNumber(categories.output),
      reasoning: asNumber(categories.reasoning),
    },
    category_pct: {
      system: asNumber(categoryPct.system),
      conversation: asNumber(categoryPct.conversation),
      tools: asNumber(categoryPct.tools),
      schemas: asNumber(categoryPct.schemas),
      output: asNumber(categoryPct.output),
      reasoning: asNumber(categoryPct.reasoning),
    },
    input_estimated: asNumber(bd.input_estimated),
    total_used: asNumber(bd.total_used),
    used_pct: asNumber(bd.used_pct),
  }
}

export async function fetchCloudUsage(): Promise<CloudUsageState | null> {
  try {
    const response = await fetch('/api/usage')
    if (!response.ok) return null
    const payload = (await response.json()) as Record<string, unknown>
    return parseCloudUsagePayload(payload)
  } catch {
    return null
  }
}
