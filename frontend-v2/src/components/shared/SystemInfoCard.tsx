import { useState } from 'react'
import {
  Cpu,
  Container,
  Zap,
  Database,
  Cloud,
  CloudOff,
  ChevronDown,
  ChevronRight,
  CircleDot,
} from 'lucide-react'
import { useSystemHealth } from '../../lib/useSystemHealth'
import { useAppStore } from '../../state/useAppStore'

function shortenModelName(name: string): string {
  if (!name) return 'Local Model'
  // Extract quant suffix like @q4_k_m
  const quantMatch = name.match(/@([^@]+)$/)
  const quant = quantMatch ? quantMatch[1].toLowerCase() : ''
  // Extract base name before quant
  const base = quantMatch ? name.slice(0, name.length - quantMatch[0].length) : name
  // Take the last dash-separated segment of the base as short name
  const parts = base.split(/[-_]/).filter(Boolean)
  // Look for model size (e.g. 12b, 27b) and quant
  const sizeIdx = parts.findIndex((p) => /^\d+b$/i.test(p))
  if (sizeIdx >= 0) {
    const shortBase = parts.slice(0, sizeIdx + 1).join('-')
    return quant ? `${shortBase}@${quant}` : shortBase
  }
  // Fallback: first 24 chars
  const short = base.length > 20 ? base.slice(0, 20) + '…' : base
  return quant ? `${short}@${quant}` : short
}

type Dot = 'ok' | 'warn' | 'error' | 'off'

function StatusDot({ state }: { state: Dot }) {
  const colors: Record<Dot, string> = {
    ok: 'var(--green)',
    warn: 'var(--amber)',
    error: 'var(--red)',
    off: 'var(--text-muted)',
  }
  return (
    <span
      className="sic-dot"
      style={{
        display: 'inline-block',
        width: 6,
        height: 6,
        borderRadius: '50%',
        background: colors[state],
        flexShrink: 0,
      }}
    />
  )
}

function InfoRow({
  icon,
  label,
  value,
  dot,
}: {
  icon: React.ReactNode
  label: string
  value: string
  dot: Dot
}) {
  return (
    <div className="sic-row">
      <span className="sic-icon">{icon}</span>
      <span className="sic-label">{label}</span>
      <span className="sic-spacer" />
      <StatusDot state={dot} />
      <span className="sic-value">{value}</span>
    </div>
  )
}

export function SystemInfoCard() {
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem('sic-open') !== 'false' } catch { /* ignore */ return true }
  })

  const health = useSystemHealth()
  const cloudStatus = useAppStore((s) => s.cloudStatus)
  const cloudUsage = useAppStore((s) => s.cloudUsage)

  const toggle = () => {
    const next = !open
    setOpen(next)
    try { localStorage.setItem('sic-open', String(next)) } catch { /* ignore */ }
  }

  const lmDot: Dot = health.lmStudio === 'ok' ? 'ok' : health.lmStudio === 'loading' ? 'off' : 'error'
  const podmanDot: Dot =
    health.podman === 'running' ? 'ok' :
    health.podman === 'stopped' ? 'warn' :
    health.podman === 'unavailable' ? 'off' : 'off'
  const redisDot: Dot = health.redis === 'ok' ? 'ok' : health.redis === 'loading' ? 'off' : 'error'
  const qdrantDot: Dot = health.qdrant === 'ok' ? 'ok' : health.qdrant === 'loading' ? 'off' : 'error'

  const podmanLabel =
    health.podman === 'running'
      ? `Running (${health.podmanContainers})`
      : health.podman === 'stopped'
      ? 'Stopped'
      : health.podman === 'unavailable'
      ? 'Not installed'
      : '…'

  const lmLabel = health.lmStudio === 'loading' ? '…' : health.lmStudio === 'ok' ? 'OK' : 'Offline'

  const cloudDot: Dot = cloudStatus?.available ? 'ok' : cloudStatus ? 'error' : 'off'
  const sessionCost = cloudUsage?.session?.estimated_cost_usd
  const cloudLabel = cloudStatus?.available
    ? sessionCost != null && (cloudUsage?.session.total_calls ?? 0) > 0
      ? `$${sessionCost.toFixed(3)} today`
      : 'Available'
    : cloudStatus
    ? 'Offline'
    : '…'

  return (
    <div className="system-info-card">
      <button
        type="button"
        className="sic-header"
        onClick={toggle}
        aria-expanded={open}
      >
        <CircleDot size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
        <span className="sic-title">System</span>
        <span style={{ flex: 1 }} />
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
      </button>

      {open && (
        <div className="sic-body">
          <InfoRow
            icon={<Cpu size={11} />}
            label="Model"
            value={health.modelName ? shortenModelName(health.modelName) : '…'}
            dot={health.modelName ? 'ok' : 'off'}
          />
          <InfoRow
            icon={<Container size={11} />}
            label="Podman"
            value={podmanLabel}
            dot={podmanDot}
          />
          <InfoRow
            icon={<Zap size={11} />}
            label="LM Studio"
            value={lmLabel}
            dot={lmDot}
          />
          <InfoRow
            icon={<Database size={11} />}
            label="Redis"
            value={health.redis === 'loading' ? '…' : health.redis === 'ok' ? 'OK' : 'Offline'}
            dot={redisDot}
          />
          <InfoRow
            icon={<Database size={11} />}
            label="Qdrant"
            value={health.qdrant === 'loading' ? '…' : health.qdrant === 'ok' ? 'OK' : 'Offline'}
            dot={qdrantDot}
          />
          <InfoRow
            icon={cloudStatus?.available ? <Cloud size={11} /> : <CloudOff size={11} />}
            label="Cloud"
            value={cloudLabel}
            dot={cloudDot}
          />
        </div>
      )}
    </div>
  )
}
