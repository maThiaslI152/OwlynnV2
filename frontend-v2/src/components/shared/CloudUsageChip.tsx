import { useEffect, useRef, useState } from 'react'
import { useAppStore, type ContextBreakdown } from '../../state/useAppStore'

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

const CATEGORY_META: Array<{
  key: keyof ContextBreakdown['categories']
  label: string
  color: string
}> = [
  { key: 'system', label: 'System', color: 'var(--purple, #a78bfa)' },
  { key: 'conversation', label: 'Conversation', color: 'var(--accent)' },
  { key: 'tools', label: 'Tools', color: 'var(--amber)' },
  { key: 'schemas', label: 'Schemas', color: 'var(--blue)' },
  { key: 'output', label: 'Output', color: 'var(--green)' },
  { key: 'reasoning', label: 'Reasoning', color: 'var(--text-secondary)' },
]

function ContextBreakdownView({ breakdown }: { breakdown: ContextBreakdown }) {
  const rows = CATEGORY_META.filter(
    ({ key }) => (breakdown.categories[key] ?? 0) > 0 || (breakdown.category_pct[key] ?? 0) > 0
  )

  return (
    <div className="cloud-usage-popover-breakdown" data-testid="context-breakdown">
      <div className="cloud-usage-popover-headline">
        <span>
          {formatTokens(breakdown.total_used)} / {formatTokens(breakdown.max_context)}
        </span>
        <span className="cloud-usage-popover-pct">{breakdown.used_pct}%</span>
      </div>
      <div
        className="cloud-usage-context-bar"
        data-testid="context-breakdown-bar"
        aria-hidden
      >
        {rows.map(({ key, color }) => {
          const pct = breakdown.category_pct[key] ?? 0
          if (pct <= 0) return null
          return (
            <div
              key={key}
              className="cloud-usage-context-segment"
              style={{ width: `${pct}%`, background: color }}
              title={`${key}: ${pct}%`}
            />
          )
        })}
      </div>
      <ul className="cloud-usage-context-rows">
        {rows.map(({ key, label, color }) => (
          <li key={key} className="cloud-usage-context-row">
            <span className="cloud-usage-context-swatch" style={{ background: color }} />
            <span className="cloud-usage-context-label">{label}</span>
            <span className="cloud-usage-context-value">
              {formatTokens(breakdown.categories[key] ?? 0)}
            </span>
            <span className="cloud-usage-context-pct">
              {(breakdown.category_pct[key] ?? 0).toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function CloudUsageChip() {
  const cloudUsage = useAppStore((s) => s.cloudUsage)
  const contextBreakdown = useAppStore((s) => s.contextBreakdown)
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDocClick = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  if (!cloudUsage || cloudUsage.session.total_calls <= 0) return null

  const session = cloudUsage.session

  return (
    <div className="cloud-usage-chip-wrap" ref={rootRef}>
      <button
        type="button"
        className="cloud-usage-chip"
        data-testid="cloud-usage-chip"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((v) => !v)}
        title="Session cost — click for context breakdown"
      >
        ${session.estimated_cost_usd.toFixed(3)}
      </button>
      {open && (
        <div
          className="cloud-usage-popover"
          role="dialog"
          aria-label="Cloud usage and context"
          data-testid="cloud-usage-popover"
        >
          <div className="cloud-usage-popover-header">
            <span className="cloud-usage-popover-title">Cloud usage</span>
            <span className="cloud-usage-popover-cost">
              {formatCost(session.estimated_cost_usd)}
            </span>
          </div>
          <p className="cloud-usage-popover-meta">
            in {formatTokens(session.prompt_tokens)} · out{' '}
            {formatTokens(session.completion_tokens)}
            {session.cache_hit_ratio > 0
              ? ` · cache ${(session.cache_hit_ratio * 100).toFixed(0)}%`
              : ''}
          </p>
          {contextBreakdown ? (
            <>
              <p className="cloud-usage-popover-subtitle">Last request context</p>
              <ContextBreakdownView breakdown={contextBreakdown} />
            </>
          ) : (
            <p className="cloud-usage-popover-empty" data-testid="context-breakdown-empty">
              Send a cloud turn to see context breakdown.
            </p>
          )}
          {cloudUsage.budget?.daily_token_limit > 0 && (
            <p className="cloud-usage-popover-daily">
              Daily: {formatTokens(cloudUsage.budget.used_tokens)} /{' '}
              {formatTokens(cloudUsage.budget.daily_token_limit)} (
              {Math.min(100, Math.round((cloudUsage.budget.used_pct ?? 0) * 100))}%)
            </p>
          )}
        </div>
      )}
    </div>
  )
}
