import { useAppStore } from '../state/useAppStore'

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

function formatCost(usd: number): string {
  if (usd >= 1) return `$${usd.toFixed(3)}`
  if (usd >= 0.01) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(6)}`
}

export function CloudUsagePanel() {
  const cloudUsage = useAppStore((s) => s.cloudUsage)

  if (!cloudUsage) {
    return (
      <p className="safe-mode-info" data-testid="cloud-usage-empty">
        No cloud usage yet this session.
      </p>
    )
  }

  const session = cloudUsage.session
  const budget = cloudUsage.budget
  const lastTurn = cloudUsage.lastTurn
  const usedPct = Math.min(100, Math.round((budget?.used_pct ?? 0) * 100))
  const budgetLimit = budget?.daily_token_limit ?? 0

  return (
    <div className="cloud-usage-panel" data-testid="cloud-usage-panel">
      <div className="cloud-usage-summary">
        <span className="cloud-usage-cost" data-testid="cloud-usage-cost">
          {formatCost(session.estimated_cost_usd)}
        </span>
        <span className="cloud-usage-tokens">
          in {formatTokens(session.prompt_tokens)} · out{' '}
          {formatTokens(session.completion_tokens)}
        </span>
        {session.cache_hit_ratio > 0 && (
          <span className="cloud-usage-cache">
            cache {(session.cache_hit_ratio * 100).toFixed(0)}%
          </span>
        )}
      </div>
      {budgetLimit > 0 && (
        <div className="cloud-usage-budget">
          <div className="cloud-usage-budget-bar">
            <div
              className="cloud-usage-budget-fill"
              style={{ width: `${usedPct}%` }}
              data-testid="cloud-usage-budget-fill"
            />
          </div>
          <span className="cloud-usage-budget-label">
            {formatTokens(budget?.used_tokens ?? 0)} / {formatTokens(budgetLimit)} daily
            ({usedPct}%)
          </span>
        </div>
      )}
      <p className="cloud-usage-meta">
        {session.total_calls} call{session.total_calls === 1 ? '' : 's'}
        {session.failed_calls > 0 ? ` · ${session.failed_calls} failed` : ''}
      </p>
      {lastTurn && (
        <details className="cloud-usage-last-turn">
          <summary>Last call</summary>
          <p>
            {formatCost(lastTurn.estimated_cost_usd ?? 0)} · in{' '}
            {formatTokens(lastTurn.prompt_tokens)} · out{' '}
            {formatTokens(lastTurn.completion_tokens)}
            {lastTurn.model_tier ? ` · ${lastTurn.model_tier}` : ''}
          </p>
        </details>
      )}
    </div>
  )
}
